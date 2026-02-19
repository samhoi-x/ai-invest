"""Market breadth analysis using a diversified S&P 500 proxy basket.

Breadth measures overall market health — how many stocks are participating
in a rally or selloff — rather than just looking at an index price.
Poor breadth (few stocks above 200MA, many decliners) is a warning sign
even when indexes look fine.

Metrics
-------
pct_above_200ma  : fraction of basket stocks trading above their 200-day SMA
ad_ratio         : advancers / (advancers + decliners) on the latest day
composite_score  : -1.0 (POOR) to +1.0 (HEALTHY)

Regime thresholds
-----------------
HEALTHY  : score >  0.30
NEUTRAL  : score between -0.20 and +0.30
WEAK     : score between -0.50 and -0.20
POOR     : score <= -0.50

Confidence modifiers applied in signal_combiner
------------------------------------------------
POOR market:  BUY confidence × 0.75
WEAK market:  BUY confidence × 0.88
HEALTHY/NEUTRAL: no adjustment (do not perversely discourage selling)

Public API
----------
get_market_breadth() -> dict   (4-hour cached, never raises)
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Representative 25-stock S&P 500 proxy basket ─────────────────────────────
# Diversified across all 11 GICS sectors to approximate market-wide breadth
BREADTH_BASKET = [
    # Technology (5)
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL",
    # Financials (4)
    "JPM", "BAC", "V", "GS",
    # Healthcare (3)
    "UNH", "JNJ", "LLY",
    # Consumer Discretionary (3)
    "AMZN", "TSLA", "HD",
    # Communication Services (2)
    "GOOGL", "META",
    # Industrials (2)
    "CAT", "BA",
    # Consumer Staples (2)
    "PG", "KO",
    # Energy (2)
    "XOM", "CVX",
    # Utilities + Materials (2)
    "NEE", "LIN",
]

_CACHE_TTL = 4 * 3600   # 4 hours
_cache: dict = {"data": None, "expires_at": 0.0}

_NEUTRAL_BREADTH = {
    "score": 0.0,
    "regime": "NEUTRAL",
    "pct_above_200ma": None,
    "ad_ratio": None,
    "advance_count": None,
    "decline_count": None,
    "neutral_count": None,
    "basket_total": 0,
    "fetched_count": 0,
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_one(symbol: str) -> Optional[dict]:
    """Fetch the latest close, 200-day SMA, and daily change for one symbol."""
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="1y", interval="1d")
        if hist is None or hist.empty or len(hist) < 10:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        sma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else float(closes.mean())
        return {
            "symbol": symbol,
            "close": latest,
            "prev_close": prev,
            "sma200": sma200,
            "above_200ma": latest > sma200,
            "daily_change": latest - prev,
        }
    except Exception as exc:
        logger.debug("Breadth fetch failed for %s: %s", symbol, exc)
        return None


def _regime_label(score: float) -> str:
    if score > 0.30:
        return "HEALTHY"
    elif score > -0.20:
        return "NEUTRAL"
    elif score > -0.50:
        return "WEAK"
    else:
        return "POOR"


# ── Public API ────────────────────────────────────────────────────────────────

def get_market_breadth() -> dict:
    """Return market breadth signal from S&P 500 proxy basket (4-hour cached).

    Returns
    -------
    dict with keys:
        score          float  -1 (POOR) to +1 (HEALTHY)
        regime         str    HEALTHY / NEUTRAL / WEAK / POOR
        pct_above_200ma float  0-1, fraction above 200-day SMA
        ad_ratio       float  0-1, advancers / total
        advance_count  int
        decline_count  int
        neutral_count  int
        basket_total   int    number of stocks in basket
        fetched_count  int    number successfully fetched
    """
    now = time.monotonic()
    if _cache["data"] is not None and now < _cache["expires_at"]:
        return _cache["data"]

    logger.info("Fetching market breadth for %d-stock basket…", len(BREADTH_BASKET))

    results = []
    # Parallel fetch — stays well within yfinance rate limits for this basket size
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, sym): sym for sym in BREADTH_BASKET}
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                results.append(res)

    if not results:
        logger.warning("Market breadth: no data fetched, returning neutral")
        breadth = dict(_NEUTRAL_BREADTH)
        _cache["data"] = breadth
        _cache["expires_at"] = now + _CACHE_TTL
        return breadth

    fetched = len(results)
    above_200 = sum(1 for r in results if r["above_200ma"])
    pct_above = above_200 / fetched

    advances = sum(1 for r in results if r["daily_change"] > 0)
    declines  = sum(1 for r in results if r["daily_change"] < 0)
    neutrals  = fetched - advances - declines
    ad_ratio  = advances / fetched

    # Score: weighted combo of 200MA position (60%) and A/D ratio (40%)
    above_score = 2 * pct_above - 1   # 0–1 → -1 to +1
    ad_score    = 2 * ad_ratio   - 1  # 0–1 → -1 to +1
    composite   = float(np.clip(0.60 * above_score + 0.40 * ad_score, -1.0, 1.0))

    breadth = {
        "score":           round(composite, 4),
        "regime":          _regime_label(composite),
        "pct_above_200ma": round(pct_above, 4),
        "ad_ratio":        round(ad_ratio, 4),
        "advance_count":   advances,
        "decline_count":   declines,
        "neutral_count":   neutrals,
        "basket_total":    len(BREADTH_BASKET),
        "fetched_count":   fetched,
    }

    logger.info(
        "Market breadth: score=%.3f regime=%s "
        "above_200ma=%.0f%% A/D=%d/%d",
        composite, breadth["regime"],
        pct_above * 100, advances, declines,
    )

    _cache["data"] = breadth
    _cache["expires_at"] = now + _CACHE_TTL
    return breadth
