"""Macro-economic signal module.

Fetches VIX (market fear), yield curve (10Y-3M spread), and DXY (USD strength)
and combines them into a single macro environment score (-1 to +1).

Public API
----------
get_macro_signal()         → dict  (4-hour cached composite macro signal)
build_macro_feature_df()   → pd.DataFrame  (date-indexed, for ML feature merging)
"""

import logging
import time
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Module-level 4-hour cache (simple dict, thread-safe enough for dashboard) ──
_CACHE_TTL_SECONDS = 4 * 3600
_cache: dict = {"signal": None, "expires_at": 0.0}

_NEUTRAL_MACRO = {
    "score": 0.0,
    "confidence": 0.0,
    "regime": "UNKNOWN",
    "vix_score": 0.0,
    "yield_score": 0.0,
    "dxy_score": 0.0,
    "vix_level": None,
    "vix_change_20d": None,
    "yield_spread": None,
    "dxy_change_20d": None,
    "sub_weights": {"vix": 0.50, "yield": 0.30, "dxy": 0.20},
    "fetched_sources": [],
}


# ── Sub-signal scoring helpers ─────────────────────────────────────────────────

def _score_vix(vix_level: float, vix_change_20d: Optional[float]) -> float:
    """Score VIX on a -1 to +1 scale.

    High VIX (fear) → negative score; low VIX (complacency) → positive score.
    """
    # Base score from VIX level
    if vix_level > 40:
        base = -1.0
    elif vix_level > 30:
        # Linear: 30→-0.75, 40→-1.0
        base = -0.75 - 0.025 * (vix_level - 30)
    elif vix_level > 20:
        # Linear: 20→-0.20, 30→-0.50
        base = -0.20 - 0.030 * (vix_level - 20)
    elif vix_level > 15:
        # Linear: 15→0.0, 20→-0.20
        base = 0.0 - 0.040 * (vix_level - 15)
    elif vix_level > 12:
        # Linear: 12→+0.30, 15→+0.10
        base = 0.30 - (0.20 / 3) * (vix_level - 12)
    else:
        base = 0.30

    # Adjustment from 20-day rate of change
    roc_adj = 0.0
    if vix_change_20d is not None:
        # Rising VIX: penalty up to -0.2; falling VIX: bonus up to +0.2
        roc_adj = float(np.clip(-vix_change_20d / 50.0, -0.2, 0.2))

    return float(np.clip(base + roc_adj, -1.0, 1.0))


def _score_yield(spread: float) -> float:
    """Score yield curve spread (10Y − 3M, in %) on a -1 to +1 scale.

    Inverted curve (negative spread) → negative score; steep curve → positive.
    """
    if spread < -0.5:
        return -0.6
    elif spread < 0.0:
        # Linear: -0.5→-0.60, 0→-0.30
        return -0.30 - 0.60 * (-spread / 0.5)
    elif spread < 0.5:
        # Linear: 0→-0.20, 0.5→0.0
        return -0.20 + 0.40 * (spread / 0.5)
    elif spread < 2.0:
        # Linear: 0.5→+0.10, 2.0→+0.40
        return 0.10 + (0.30 / 1.5) * (spread - 0.5)
    else:
        return 0.40


def _score_dxy(dxy_change_20d: float) -> float:
    """Score DXY 20-day % change on a -1 to +1 scale.

    Strong USD rise → negative for risk assets; weak USD → positive.
    """
    pct = dxy_change_20d  # e.g. 3.5 means +3.5%
    if pct > 5.0:
        return -0.30
    elif pct > 2.0:
        # Linear: +2→-0.10, +5→-0.30
        return -0.10 - (0.20 / 3.0) * (pct - 2.0)
    elif pct > -2.0:
        return 0.0
    elif pct > -5.0:
        # Linear: -2→+0.10, -5→+0.30
        return 0.10 + (0.20 / 3.0) * (-pct - 2.0)
    else:
        return 0.30


def _regime_label(score: float) -> str:
    if score <= -0.4:
        return "RISK_OFF"
    elif score <= -0.1:
        return "CAUTIOUS"
    elif score <= 0.1:
        return "NEUTRAL"
    elif score <= 0.35:
        return "CONSTRUCTIVE"
    else:
        return "RISK_ON"


# ── Data fetching helpers ──────────────────────────────────────────────────────

def _fetch_vix_data(period: str = "3mo") -> tuple[Optional[float], Optional[float]]:
    """Return (current VIX level, 20-day % change). Both may be None on error."""
    import yfinance as yf
    ticker = yf.Ticker("^VIX")
    hist = ticker.history(period=period)
    if hist is None or hist.empty:
        return None, None
    closes = hist["Close"].dropna()
    if len(closes) == 0:
        return None, None
    current = float(closes.iloc[-1])
    change_20d = None
    if len(closes) >= 21:
        prev = float(closes.iloc[-21])
        if prev > 0:
            change_20d = (current - prev) / prev * 100.0
    return current, change_20d


def _fetch_yield_spread(period: str = "3mo") -> Optional[float]:
    """Return 10Y - 3M Treasury spread in %, or None on error."""
    import yfinance as yf
    tnx = yf.Ticker("^TNX").history(period=period)
    irx = yf.Ticker("^IRX").history(period=period)
    if tnx is None or tnx.empty or irx is None or irx.empty:
        return None
    tnx_close = tnx["Close"].dropna()
    irx_close = irx["Close"].dropna()
    if len(tnx_close) == 0 or len(irx_close) == 0:
        return None
    # ^TNX and ^IRX quote in percentage points (e.g. 4.25 = 4.25%)
    spread = float(tnx_close.iloc[-1]) - float(irx_close.iloc[-1])
    return spread


def _fetch_dxy_change(period: str = "3mo") -> Optional[float]:
    """Return DXY 20-day % change, or None on error."""
    import yfinance as yf
    hist = yf.Ticker("DX-Y.NYB").history(period=period)
    if hist is None or hist.empty:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 21:
        return None
    current = float(closes.iloc[-1])
    prev = float(closes.iloc[-21])
    if prev == 0:
        return None
    return (current - prev) / prev * 100.0


# ── Public API ─────────────────────────────────────────────────────────────────

def get_macro_signal() -> dict:
    """Return a composite macro environment signal (4-hour cached).

    Each of the three sub-fetches (VIX, yield curve, DXY) is individually
    try/excepted so a single API failure degrades confidence without crashing.

    Returns
    -------
    dict with keys:
        score          float  -1 (very bearish) to +1 (very bullish)
        confidence     float   0 to 1
        regime         str    RISK_OFF / CAUTIOUS / NEUTRAL / CONSTRUCTIVE / RISK_ON / UNKNOWN
        vix_score      float
        yield_score    float
        dxy_score      float
        vix_level      float | None
        vix_change_20d float | None   (% change over 20 trading days)
        yield_spread   float | None   (10Y - 3M, in %)
        dxy_change_20d float | None   (% change over 20 trading days)
        sub_weights    dict
        fetched_sources list[str]
    """
    now = time.monotonic()
    if _cache["signal"] is not None and now < _cache["expires_at"]:
        return _cache["signal"]

    weights = {"vix": 0.50, "yield": 0.30, "dxy": 0.20}
    fetched_sources: list[str] = []

    vix_level: Optional[float] = None
    vix_change_20d: Optional[float] = None
    vix_score: float = 0.0

    yield_spread: Optional[float] = None
    yield_score: float = 0.0

    dxy_change_20d: Optional[float] = None
    dxy_score: float = 0.0

    # ── VIX ──────────────────────────────────────────────────────────────
    try:
        vix_level, vix_change_20d = _fetch_vix_data()
        if vix_level is not None:
            vix_score = _score_vix(vix_level, vix_change_20d)
            fetched_sources.append("VIX")
            logger.debug("VIX: level=%.2f change_20d=%s score=%.3f",
                         vix_level, vix_change_20d, vix_score)
    except Exception as exc:
        logger.warning("Macro VIX fetch failed: %s", exc)

    # ── Yield Curve ───────────────────────────────────────────────────────
    try:
        yield_spread = _fetch_yield_spread()
        if yield_spread is not None:
            yield_score = _score_yield(yield_spread)
            fetched_sources.append("YIELD")
            logger.debug("Yield spread: %.3f%% → score=%.3f", yield_spread, yield_score)
    except Exception as exc:
        logger.warning("Macro yield curve fetch failed: %s", exc)

    # ── DXY ───────────────────────────────────────────────────────────────
    try:
        dxy_change_20d = _fetch_dxy_change()
        if dxy_change_20d is not None:
            dxy_score = _score_dxy(dxy_change_20d)
            fetched_sources.append("DXY")
            logger.debug("DXY 20d change: %.2f%% → score=%.3f", dxy_change_20d, dxy_score)
    except Exception as exc:
        logger.warning("Macro DXY fetch failed: %s", exc)

    # ── Composite ─────────────────────────────────────────────────────────
    if not fetched_sources:
        # Total failure — return neutral with zero confidence
        logger.warning("All macro sub-fetches failed; returning neutral macro signal")
        signal = dict(_NEUTRAL_MACRO)
        _cache["signal"] = signal
        _cache["expires_at"] = now + _CACHE_TTL_SECONDS
        return signal

    # Missing sources reduce confidence by 1/3 each
    missing_count = 3 - len(fetched_sources)
    confidence = max(0.0, 1.0 - missing_count / 3.0)

    composite = (weights["vix"]   * vix_score +
                 weights["yield"] * yield_score +
                 weights["dxy"]   * dxy_score)
    composite = float(np.clip(composite, -1.0, 1.0))

    signal = {
        "score": round(composite, 4),
        "confidence": round(confidence, 4),
        "regime": _regime_label(composite),
        "vix_score": round(vix_score, 4),
        "yield_score": round(yield_score, 4),
        "dxy_score": round(dxy_score, 4),
        "vix_level": round(vix_level, 2) if vix_level is not None else None,
        "vix_change_20d": round(vix_change_20d, 2) if vix_change_20d is not None else None,
        "yield_spread": round(yield_spread, 3) if yield_spread is not None else None,
        "dxy_change_20d": round(dxy_change_20d, 2) if dxy_change_20d is not None else None,
        "sub_weights": weights,
        "fetched_sources": fetched_sources,
    }

    logger.info(
        "Macro signal: score=%.3f regime=%s conf=%.2f (sources=%s)",
        signal["score"], signal["regime"], signal["confidence"],
        ",".join(fetched_sources),
    )

    _cache["signal"] = signal
    _cache["expires_at"] = now + _CACHE_TTL_SECONDS
    return signal


def build_macro_feature_df(period: str = "2y") -> pd.DataFrame:
    """Build a date-indexed DataFrame with macro features for ML merging.

    Columns
    -------
    VIX_level       : daily VIX closing level
    VIX_change_20d  : 20-day rolling % change in VIX
    yield_spread    : 10Y - 3M Treasury spread (%)
    dxy_change_20d  : 20-day rolling % change in DXY

    Returns an empty DataFrame if all fetches fail.
    """
    import yfinance as yf

    frames: list[pd.DataFrame] = []

    # VIX
    try:
        vix_hist = yf.Ticker("^VIX").history(period=period)
        if vix_hist is not None and not vix_hist.empty:
            vix_close = vix_hist["Close"].rename("VIX_level")
            vix_roc = vix_close.pct_change(20) * 100
            vix_roc.name = "VIX_change_20d"
            frames.append(pd.concat([vix_close, vix_roc], axis=1))
    except Exception as exc:
        logger.warning("build_macro_feature_df: VIX fetch failed: %s", exc)

    # Yield spread
    try:
        tnx = yf.Ticker("^TNX").history(period=period)["Close"]
        irx = yf.Ticker("^IRX").history(period=period)["Close"]
        spread = (tnx - irx).rename("yield_spread")
        frames.append(spread.to_frame())
    except Exception as exc:
        logger.warning("build_macro_feature_df: yield spread fetch failed: %s", exc)

    # DXY
    try:
        dxy_hist = yf.Ticker("DX-Y.NYB").history(period=period)
        if dxy_hist is not None and not dxy_hist.empty:
            dxy_roc = dxy_hist["Close"].pct_change(20) * 100
            dxy_roc.name = "dxy_change_20d"
            frames.append(dxy_roc.to_frame())
    except Exception as exc:
        logger.warning("build_macro_feature_df: DXY fetch failed: %s", exc)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, axis=1)
    # Normalise index to tz-naive date
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df.index = pd.to_datetime(df.index).normalize()
    df = df.sort_index()
    return df
