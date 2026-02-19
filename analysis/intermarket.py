"""Cross-asset (inter-market) correlation and regime signal.

Tracks five key cross-asset indicators to detect whether the macro environment
is risk-on or risk-off, and whether there are leading-indicator signals from
related asset classes.

Assets tracked
--------------
BTC-USD   Risk appetite proxy — early warning for tech/growth sentiment
DX-Y.NYB  USD strength — headwind for multinational earners and commodities
GLD       Gold — safe-haven demand; rising gold + falling stocks = fear
USO       Oil — commodity cycle; affects energy, transport, consumer margins
TLT       20Y Treasury — rate sensitivity; rising TLT = falling yields = risk-off

Cross-asset scoring (all mapped to -1 bullish headwind → +1 bullish tailwind)
-------------------------------------------------------------------------------
BTC  20d >+10% → +0.30 (risk-on)  |  <-10% → -0.30 (risk-off)
DXY  20d >+3%  → -0.25 (headwind) |  <-3%  → +0.25 (tailwind)
Gold 20d >+5%  → -0.20 (fear)     |  <-2%  → +0.10 (calm)
Oil  20d >+10% → -0.10 (cost push)|  <-10% → +0.15 (relief)
TLT  20d >+3%  → +0.20 (rates ↓)  |  <-3%  → -0.20 (rates ↑)

Regime
------
RISK_ON     score >  0.25
NEUTRAL    -0.15 ≤ score ≤ 0.25
RISK_OFF    score < -0.15

Public API
----------
get_intermarket_signal() -> dict   (4-hour cached, never raises)
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_TTL = 4 * 3600
_cache: dict = {"signal": None, "expires_at": 0.0}

_ASSETS = {
    "BTC":  "BTC-USD",
    "DXY":  "DX-Y.NYB",
    "Gold": "GLD",
    "Oil":  "USO",
    "TLT":  "TLT",
}

_NEUTRAL_SIGNAL = {
    "score": 0.0,
    "regime": "NEUTRAL",
    "confidence": 0.0,
    "btc_20d":  None,
    "dxy_20d":  None,
    "gold_20d": None,
    "oil_20d":  None,
    "tlt_20d":  None,
    "component_scores": {},
    "fetched_assets": [],
}


# ── Asset scoring ─────────────────────────────────────────────────────────────

def _score_btc(ret20: float) -> float:
    """BTC 20d return → bullishness for risk assets."""
    if ret20 > 10:
        return 0.30
    elif ret20 > 5:
        return 0.15 + 0.03 * (ret20 - 5)
    elif ret20 > -5:
        return ret20 * 0.03       # linear ±0.15
    elif ret20 > -10:
        return -0.15 - 0.03 * (-ret20 - 5)
    else:
        return -0.30


def _score_dxy(ret20: float) -> float:
    """DXY 20d return → headwind (negative) or tailwind (positive)."""
    if ret20 > 3:
        return -0.25
    elif ret20 > 1:
        return -0.25 * (ret20 - 1) / 2
    elif ret20 > -1:
        return 0.0
    elif ret20 > -3:
        return 0.25 * (-ret20 - 1) / 2
    else:
        return 0.25


def _score_gold(ret20: float) -> float:
    """Gold 20d return — rising gold signals fear, bearish for risk assets."""
    if ret20 > 5:
        return -0.20
    elif ret20 > 2:
        return -0.20 * (ret20 - 2) / 3
    elif ret20 > -2:
        return 0.0
    else:
        return 0.10


def _score_oil(ret20: float) -> float:
    """Oil 20d return — cost-push inflation headwind vs demand/relief signal."""
    if ret20 > 10:
        return -0.10
    elif ret20 > 3:
        return -0.10 * (ret20 - 3) / 7
    elif ret20 > -5:
        return 0.0
    elif ret20 > -10:
        return 0.15 * (-ret20 - 5) / 5
    else:
        return 0.15


def _score_tlt(ret20: float) -> float:
    """TLT (20Y Treasury) 20d return — rates proxy."""
    # TLT up = yields falling = bonds rallying = risk-off environment UNLESS
    # driven by Fed easing, which can be risk-on.
    # Conservative: TLT up → cautious; TLT down → rates rising → headwind for equities
    if ret20 > 3:
        return 0.20    # Yields fell sharply — deflationary / Fed pivot signal
    elif ret20 > 1:
        return 0.10 * (ret20 - 1) / 2
    elif ret20 > -1:
        return 0.0
    elif ret20 > -3:
        return -0.20 * (-ret20 - 1) / 2
    else:
        return -0.20


_SCORERS = {
    "BTC":  (_score_btc,  0.30),
    "DXY":  (_score_dxy,  0.25),
    "Gold": (_score_gold, 0.20),
    "Oil":  (_score_oil,  0.10),
    "TLT":  (_score_tlt,  0.15),
}


def _regime_label(score: float) -> str:
    if score > 0.25:
        return "RISK_ON"
    elif score > -0.15:
        return "NEUTRAL"
    else:
        return "RISK_OFF"


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_20d_return(name: str, ticker: str) -> Optional[tuple[str, float]]:
    """Return (name, 20-day % change) or None on failure."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="3mo", interval="1d")
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 21:
            return None
        ret = (float(closes.iloc[-1]) / float(closes.iloc[-21]) - 1) * 100
        return name, round(ret, 2)
    except Exception as exc:
        logger.debug("Intermarket fetch failed for %s (%s): %s", name, ticker, exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_intermarket_signal() -> dict:
    """Return cross-asset regime signal (4-hour cached, never raises).

    Returns
    -------
    dict with keys:
        score              float  -1 (strong headwind) to +1 (strong tailwind)
        regime             str    RISK_ON / NEUTRAL / RISK_OFF
        confidence         float  0-1 (based on number of assets fetched)
        btc_20d / dxy_20d / gold_20d / oil_20d / tlt_20d   float | None
        component_scores   dict   {asset: score}
        fetched_assets     list[str]
    """
    now = time.monotonic()
    if _cache["signal"] is not None and now < _cache["expires_at"]:
        return _cache["signal"]

    # Parallel fetch of all five assets
    returns: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_20d_return, name, ticker): name
                   for name, ticker in _ASSETS.items()}
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                name, ret = res
                returns[name] = ret

    if not returns:
        logger.warning("Intermarket: no assets fetched, returning neutral")
        sig = dict(_NEUTRAL_SIGNAL)
        _cache["signal"] = sig
        _cache["expires_at"] = now + _CACHE_TTL
        return sig

    # Score each asset
    component_scores: dict[str, float] = {}
    total_w = 0.0
    weighted_sum = 0.0

    for name, (scorer, weight) in _SCORERS.items():
        if name in returns:
            s = scorer(returns[name])
            component_scores[name] = round(s, 4)
            weighted_sum += weight * s
            total_w += weight

    composite = float(np.clip(weighted_sum / total_w, -1.0, 1.0)) if total_w > 0 else 0.0
    confidence = round(len(returns) / len(_ASSETS), 4)

    signal = {
        "score":             round(composite, 4),
        "regime":            _regime_label(composite),
        "confidence":        confidence,
        "btc_20d":           returns.get("BTC"),
        "dxy_20d":           returns.get("DXY"),
        "gold_20d":          returns.get("Gold"),
        "oil_20d":           returns.get("Oil"),
        "tlt_20d":           returns.get("TLT"),
        "component_scores":  component_scores,
        "fetched_assets":    list(returns.keys()),
    }

    logger.info(
        "Intermarket: score=%.3f regime=%s (BTC=%s DXY=%s Gold=%s Oil=%s TLT=%s)",
        composite, signal["regime"],
        returns.get("BTC"), returns.get("DXY"), returns.get("Gold"),
        returns.get("Oil"), returns.get("TLT"),
    )

    _cache["signal"] = signal
    _cache["expires_at"] = now + _CACHE_TTL
    return signal
