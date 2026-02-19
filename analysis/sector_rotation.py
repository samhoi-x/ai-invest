"""Sector Rotation Signal — relative sector strength vs SPY.

Tracks the 11 SPDR sector ETFs and measures which sectors are outperforming
(LEADING) or underperforming (LAGGING) the broad market (SPY).  Individual
stock signals are then given a small tailwind or headwind modifier based on
their sector's current momentum.

Sector ETFs tracked
-------------------
XLK  Technology          XLF  Financials       XLE  Energy
XLV  Healthcare          XLI  Industrials      XLY  Consumer Discr.
XLP  Consumer Staples    XLU  Utilities        XLRE Real Estate
XLB  Materials           XLC  Communication

Relative-strength scoring per sector
-------------------------------------
For each sector, compute log relative return vs SPY over 3 windows:
  1-month (21d): weight 0.20
  3-month (63d): weight 0.50
  6-month (126d): weight 0.30

Composite relative strength is z-scored across all 11 sectors and then
mapped to [-1, +1] using a tanh clip (z ÷ 1.5 clipped at ±1).

Sector regime
  LEADING  score >  0.15
  NEUTRAL  score ∈ [-0.15, 0.15]
  LAGGING  score < -0.15

Individual stock modifier
  If a stock's sector is LEADING:  composite += +0.05
  If a stock's sector is LAGGING:  composite -= 0.05

Public API
----------
get_sector_signal(symbol, asset_type="stock") -> dict   (4-hour cached)
get_sector_rotation_overview() -> dict                  (4-hour cached)
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_CACHE_TTL = 4 * 3600

_SECTOR_ETFS: dict[str, str] = {
    "Technology":       "XLK",
    "Financials":       "XLF",
    "Energy":           "XLE",
    "Healthcare":       "XLV",
    "Industrials":      "XLI",
    "ConsumerDiscr":    "XLY",
    "ConsumerStaples":  "XLP",
    "Utilities":        "XLU",
    "RealEstate":       "XLRE",
    "Materials":        "XLB",
    "Communication":    "XLC",
}

# Ticker → sector mapping for default watchlist (avoids per-stock yfinance calls)
_STOCK_SECTOR_MAP: dict[str, str] = {
    "AAPL":  "Technology",    "MSFT":  "Technology",    "NVDA":  "Technology",
    "GOOGL": "Communication", "META":  "Communication",
    "AMZN":  "ConsumerDiscr", "TSLA":  "ConsumerDiscr",
    "JPM":   "Financials",    "GS":    "Financials",    "BAC":   "Financials",
    "XOM":   "Energy",        "CVX":   "Energy",
    "JNJ":   "Healthcare",    "PFE":   "Healthcare",
    "SPY":   None,            "QQQ":   None,            "DIA":   None,
}

_RS_WEIGHTS = {"1m": 0.20, "3m": 0.50, "6m": 0.30}

_overview_cache: dict = {"data": None, "expires_at": 0.0}


# ── Relative-strength helpers ─────────────────────────────────────────────────

def _fetch_closes(ticker: str, period: str = "7mo") -> Optional[pd.Series]:
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=period, interval="1d")
        if hist is None or hist.empty:
            return None
        return hist["Close"].dropna()
    except Exception as exc:
        logger.debug("Sector fetch failed for %s: %s", ticker, exc)
        return None


def _rel_return(sector_closes: pd.Series, spy_closes: pd.Series,
                window: int) -> float:
    """Log relative return of sector vs SPY over the last `window` trading days."""
    if len(sector_closes) < window + 1 or len(spy_closes) < window + 1:
        return 0.0
    sec_ret = np.log(sector_closes.iloc[-1] / sector_closes.iloc[-window])
    spy_ret = np.log(spy_closes.iloc[-1] / spy_closes.iloc[-window])
    return float(sec_ret - spy_ret)


# ── Overview computation ──────────────────────────────────────────────────────

def _compute_overview() -> dict:
    """Fetch all sector ETFs + SPY and compute relative-strength scores."""
    spy_closes = _fetch_closes("SPY")
    if spy_closes is None:
        return {}

    def _fetch_sector(name: str, ticker: str):
        closes = _fetch_closes(ticker)
        if closes is None:
            return name, None
        rs_scores = {
            "1m":  _rel_return(closes, spy_closes, 21),
            "3m":  _rel_return(closes, spy_closes, 63),
            "6m":  _rel_return(closes, spy_closes, 126),
        }
        composite = sum(_RS_WEIGHTS[k] * v for k, v in rs_scores.items())
        return name, {"ticker": ticker, "rs_scores": rs_scores,
                      "raw_composite": composite, "closes": closes}

    raw: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_sector, n, t): n
                   for n, t in _SECTOR_ETFS.items()}
        for fut in as_completed(futures):
            name, result = fut.result()
            if result is not None:
                raw[name] = result

    if not raw:
        return {}

    # Z-score the raw composites across sectors, then clip to [-1, +1]
    composites = np.array([raw[n]["raw_composite"] for n in raw])
    mean, std = composites.mean(), composites.std()

    overview: dict[str, dict] = {}
    for name, data in raw.items():
        z = (data["raw_composite"] - mean) / (std + 1e-9)
        score = float(np.clip(np.tanh(z), -1.0, 1.0))
        regime = "LEADING" if score > 0.15 else "LAGGING" if score < -0.15 else "NEUTRAL"
        overview[name] = {
            "ticker":       data["ticker"],
            "score":        round(score, 4),
            "regime":       regime,
            "rs_1m":        round(data["rs_scores"]["1m"] * 100, 2),
            "rs_3m":        round(data["rs_scores"]["3m"] * 100, 2),
            "rs_6m":        round(data["rs_scores"]["6m"] * 100, 2),
        }

    logger.info(
        "Sector rotation: top=%s bottom=%s",
        max(overview, key=lambda k: overview[k]["score"]),
        min(overview, key=lambda k: overview[k]["score"]),
    )
    return overview


# ── Public API ────────────────────────────────────────────────────────────────

def get_sector_rotation_overview() -> dict:
    """Return relative-strength scores for all 11 sectors (4-hour cached).

    Returns
    -------
    dict  {sector_name: {ticker, score, regime, rs_1m, rs_3m, rs_6m}}
          Empty dict on total failure.
    """
    now = time.monotonic()
    if _overview_cache["data"] is not None and now < _overview_cache["expires_at"]:
        return _overview_cache["data"]

    try:
        overview = _compute_overview()
    except Exception as exc:
        logger.warning("Sector rotation overview failed: %s", exc)
        overview = {}

    _overview_cache["data"] = overview
    _overview_cache["expires_at"] = now + _CACHE_TTL
    return overview


def get_sector_for_symbol(symbol: str) -> Optional[str]:
    """Return the sector name for a stock symbol, or None if unknown/N/A."""
    clean = symbol.split("/")[0].upper()

    # Static map first (fast, no network)
    if clean in _STOCK_SECTOR_MAP:
        return _STOCK_SECTOR_MAP[clean]

    # Fallback: yfinance info lookup (cached at OS/DNS level; ~0.5s)
    try:
        import yfinance as yf
        info = yf.Ticker(clean).info
        sector = info.get("sector") or info.get("sectorDisp")
        return sector
    except Exception:
        return None


def get_sector_signal(symbol: str, asset_type: str = "stock") -> dict:
    """Return the sector rotation modifier for a specific symbol.

    Args:
        symbol:     Ticker symbol.
        asset_type: "stock" or "crypto".

    Returns
    -------
    dict with:
        score      float  Sector RS score (-1 to +1), 0 for crypto / unknown
        regime     str    LEADING / NEUTRAL / LAGGING / N/A
        sector     str    Sector name, or None
        modifier   float  Small composite modifier to apply (+0.05 / 0 / -0.05)
    """
    if asset_type == "crypto":
        return {"score": 0.0, "regime": "N/A", "sector": None, "modifier": 0.0}

    sector_name = get_sector_for_symbol(symbol)
    if sector_name is None:
        return {"score": 0.0, "regime": "N/A", "sector": None, "modifier": 0.0}

    overview = get_sector_rotation_overview()
    if not overview:
        return {"score": 0.0, "regime": "N/A", "sector": sector_name, "modifier": 0.0}

    # Fuzzy match sector name (yfinance names differ from our key names)
    matched = None
    for key in overview:
        if (sector_name.lower() in key.lower() or
                key.lower() in sector_name.lower() or
                sector_name.lower().replace(" ", "") == key.lower().replace(" ", "")):
            matched = key
            break

    if matched is None:
        return {"score": 0.0, "regime": "N/A", "sector": sector_name, "modifier": 0.0}

    data = overview[matched]
    regime = data["regime"]
    modifier = 0.05 if regime == "LEADING" else -0.05 if regime == "LAGGING" else 0.0

    return {
        "score":    data["score"],
        "regime":   regime,
        "sector":   sector_name,
        "modifier": modifier,
        "rs_1m":    data.get("rs_1m"),
        "rs_3m":    data.get("rs_3m"),
        "rs_6m":    data.get("rs_6m"),
    }
