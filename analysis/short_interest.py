"""Short Interest & Squeeze Detector.

Fetches short-interest metrics for a stock symbol via yfinance and scores
the combination of short exposure with recent price momentum.

Short-squeeze scoring logic
---------------------------
A squeeze occurs when a heavily shorted stock starts rising, forcing short
sellers to buy to cover, which accelerates the move.

    short_float > 20%  AND  momentum_5d > +3%  → squeeze alert  (+0.25)
    short_float > 20%  AND  momentum_5d > +1%  → building       (+0.15)
    short_float > 20%  AND  momentum_5d < -3%  → confirmation   (+0.10 for SELL)
    short_float 10-20% AND  momentum > 0       → mild tailwind  (+0.05)
    short_float < 5%   → no short-interest signal

Short ratio (days-to-cover) adjustments
    ratio > 10d  AND  squeeze: confidence boost +0.05 (longer squeeze duration)
    ratio > 10d  AND  confirmation: add -0.05 modifier

Public API
----------
get_short_interest_signal(symbol, price_df=None) -> dict
    24-hour per-symbol cache.  Returns neutral dict on error or for crypto.
"""

import logging
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_TTL = 24 * 3600  # yfinance short data updates weekly; 24h is fine
_cache: dict[str, dict] = {}

_NEUTRAL = {
    "score": 0.0,
    "regime": "N/A",
    "short_float": None,
    "short_ratio": None,
    "momentum_5d": None,
    "confidence": 0.0,
}


def _fetch_short_data(symbol: str) -> dict:
    """Fetch short float and short ratio from yfinance info."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        short_float = info.get("shortPercentOfFloat")  # 0.0–1.0
        short_ratio = info.get("shortRatio")           # days-to-cover
        if short_float is not None:
            short_float = float(short_float)
        if short_ratio is not None:
            short_ratio = float(short_ratio)
        return {"short_float": short_float, "short_ratio": short_ratio}
    except Exception as exc:
        logger.debug("Short interest fetch failed for %s: %s", symbol, exc)
        return {}


def _compute_momentum(price_df: Optional[pd.DataFrame]) -> Optional[float]:
    """Compute 5-day price momentum (% change) from a price DataFrame."""
    if price_df is None or price_df.empty or len(price_df) < 6:
        return None
    try:
        closes = price_df["close"].dropna()
        if len(closes) < 6:
            return None
        return float((closes.iloc[-1] / closes.iloc[-6] - 1) * 100)
    except Exception:
        return None


def get_short_interest_signal(
    symbol: str,
    asset_type: str = "stock",
    price_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Return short-interest squeeze/confirmation signal.

    Args:
        symbol:     Ticker (e.g. "AAPL"). Crypto returns neutral.
        asset_type: "stock" or "crypto".
        price_df:   Optional recent OHLCV DataFrame for momentum calculation.

    Returns
    -------
    dict with:
        score         float  Signal score (-1 to +1)
        regime        str    SQUEEZE / SQUEEZE_BUILD / BEAR_CONFIRM / MILD / NEUTRAL / N/A
        short_float   float  Short interest as fraction of float (0–1), or None
        short_ratio   float  Days-to-cover ratio, or None
        momentum_5d   float  5-day % change, or None
        confidence    float  0–1
    """
    if asset_type == "crypto":
        return dict(_NEUTRAL)

    clean = symbol.split("/")[0].upper()
    now = time.monotonic()

    entry = _cache.get(clean)
    if entry is not None and now < entry.get("expires_at", 0):
        # Recompute momentum with fresh price data if provided
        if price_df is not None:
            entry = entry.copy()
            entry["momentum_5d"] = _compute_momentum(price_df)
            entry["score"], entry["regime"] = _score_short(
                entry.get("short_float"), entry["momentum_5d"],
                entry.get("short_ratio")
            )
        return {k: v for k, v in entry.items() if k != "expires_at"}

    raw = _fetch_short_data(clean)
    short_float = raw.get("short_float")
    short_ratio = raw.get("short_ratio")
    momentum_5d = _compute_momentum(price_df)

    score, regime = _score_short(short_float, momentum_5d, short_ratio)

    if short_float is not None:
        confidence = min(0.70, 0.40 + short_float * 1.5)
    else:
        confidence = 0.0

    result = {
        "score":       round(score, 4),
        "regime":      regime,
        "short_float": round(short_float, 4) if short_float is not None else None,
        "short_ratio": round(short_ratio, 1) if short_ratio is not None else None,
        "momentum_5d": round(momentum_5d, 2) if momentum_5d is not None else None,
        "confidence":  round(confidence, 4),
    }

    _cache[clean] = {**result, "expires_at": now + _CACHE_TTL}

    logger.debug(
        "Short interest %s: float=%.1f%% ratio=%.1fd mom=%.1f%% → %s score=%.3f",
        clean,
        (short_float or 0) * 100, short_ratio or 0,
        momentum_5d or 0, regime, score,
    )
    return result


def _score_short(
    short_float: Optional[float],
    momentum_5d: Optional[float],
    short_ratio: Optional[float],
) -> tuple[float, str]:
    """Map short-interest metrics to (score, regime)."""
    if short_float is None:
        return 0.0, "N/A"

    mom = momentum_5d or 0.0
    ratio = short_ratio or 0.0

    # ── Squeeze territory (short float > 20%) ─────────────────────────────
    if short_float > 0.20:
        if mom > 3.0:
            score  = 0.25 + min(0.15, (mom - 3.0) * 0.03)
            regime = "SQUEEZE"
            if ratio > 10:
                score = min(0.50, score + 0.05)  # long cover time amplifies
        elif mom > 1.0:
            score  = 0.15
            regime = "SQUEEZE_BUILD"
        elif mom < -3.0:
            # Short sellers are winning — bearish confirmation
            score  = -0.10
            regime = "BEAR_CONFIRM"
        else:
            score  = 0.0
            regime = "HIGH_SHORT"

    # ── Elevated short interest (10–20%) ─────────────────────────────────
    elif short_float > 0.10:
        if mom > 2.0:
            score  = 0.10
            regime = "MILD_SQUEEZE"
        elif mom < -2.0:
            score  = -0.05
            regime = "MILD_CONFIRM"
        else:
            score  = 0.05
            regime = "MILD"

    # ── Low short interest (<10%) ─────────────────────────────────────────
    else:
        score  = 0.0
        regime = "NEUTRAL"

    return float(np.clip(score, -0.50, 0.50)), regime
