"""Options market sentiment — Put/Call ratio and IV skew.

Uses yfinance options chain data to assess retail/institutional positioning.

Signals
-------
Put/Call ratio (PCR) — contrarian sentiment:
  PCR > 1.5  → extreme bearish positioning → contrarian BULLISH  (+0.25)
  PCR > 1.2  → elevated fear               → mild bullish         (+0.12)
  PCR 0.8–1.2 → neutral                                           (0.0)
  PCR 0.6–0.8 → mild complacency           → mild bearish         (-0.10)
  PCR < 0.6  → extreme complacency         → contrarian BEARISH  (-0.22)

IV Skew (put IV / call IV):
  skew > 1.30 → pronounced fear premium    → contrarian bullish   (+0.08)
  skew > 1.15 → moderate put premium       → mild bullish          (+0.04)
  skew < 0.85 → call premium > put         → mildly bearish        (-0.04)
  skew < 0.70 → extreme call bias          → contrarian bearish    (-0.08)

Composite = PCR_signal + IV_skew_signal, clipped to [-0.40, +0.40].
Confidence ∈ [0.35, 0.70], higher when options data is fresher and
volume is higher.

Cache: 2-hour per-symbol (options data is end-of-day but updates intraday).

Public API
----------
get_options_signal(symbol, asset_type="stock") -> dict
    score       float  -1 to +1
    regime      str    FEAR / NEUTRAL / COMPLACENCY / N/A
    pcr         float  Put/Call volume ratio, or None
    iv_skew     float  Avg put IV / avg call IV, or None
    avg_call_iv float  Average call implied volatility
    avg_put_iv  float  Average put implied volatility
    confidence  float  0–1
"""

import logging
import time
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_CACHE_TTL = 2 * 3600  # 2-hour cache (options data updates intraday)
_cache: dict[str, dict] = {}

_NEUTRAL_OPTIONS = {
    "score":       0.0,
    "regime":      "N/A",
    "pcr":         None,
    "iv_skew":     None,
    "avg_call_iv": None,
    "avg_put_iv":  None,
    "confidence":  0.0,
}


# ── Data fetch ────────────────────────────────────────────────────────────────

def _fetch_options_data(symbol: str) -> dict:
    """Fetch nearest-expiry options chain from yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {}

        # Use nearest expiry (index 0 is soonest)
        chain = ticker.option_chain(expirations[0])
        calls = chain.calls
        puts  = chain.puts

        if calls.empty or puts.empty:
            return {}

        call_vol = calls["volume"].fillna(0).sum()
        put_vol  = puts["volume"].fillna(0).sum()
        pcr = float(put_vol / max(call_vol, 1))

        avg_call_iv = float(calls["impliedVolatility"].replace(0, np.nan).dropna().mean()) \
                      if not calls["impliedVolatility"].isna().all() else None
        avg_put_iv  = float(puts["impliedVolatility"].replace(0, np.nan).dropna().mean()) \
                      if not puts["impliedVolatility"].isna().all() else None

        iv_skew = float(avg_put_iv / avg_call_iv) \
                  if (avg_put_iv and avg_call_iv and avg_call_iv > 0) else None

        # Confidence: based on total volume
        total_vol = call_vol + put_vol
        conf_vol = min(0.70, 0.35 + total_vol / 500_000)

        return {
            "pcr":         round(pcr, 3),
            "iv_skew":     round(iv_skew, 3) if iv_skew is not None else None,
            "avg_call_iv": round(avg_call_iv, 4) if avg_call_iv is not None else None,
            "avg_put_iv":  round(avg_put_iv, 4) if avg_put_iv is not None else None,
            "confidence_vol": round(conf_vol, 4),
        }
    except Exception as exc:
        logger.debug("Options fetch failed for %s: %s", symbol, exc)
        return {}


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_pcr(pcr: float) -> float:
    """Contrarian score from put/call ratio."""
    if pcr > 1.5:
        return 0.25
    elif pcr > 1.2:
        return 0.12
    elif pcr >= 0.8:
        return 0.0
    elif pcr >= 0.6:
        return -0.10
    else:
        return -0.22


def _score_iv_skew(skew: float) -> float:
    """Score from put IV / call IV ratio."""
    if skew > 1.30:
        return 0.08
    elif skew > 1.15:
        return 0.04
    elif skew < 0.70:
        return -0.08
    elif skew < 0.85:
        return -0.04
    return 0.0


def _classify_regime(score: float) -> str:
    if score >= 0.15:
        return "FEAR"          # options market showing fear → contrarian bullish
    elif score <= -0.12:
        return "COMPLACENCY"   # options market complacent  → contrarian bearish
    else:
        return "NEUTRAL"


# ── Public API ────────────────────────────────────────────────────────────────

def get_options_signal(symbol: str, asset_type: str = "stock") -> dict:
    """Return options-based sentiment signal for a stock.

    Args:
        symbol:     Ticker (e.g. "AAPL"). Returns neutral for crypto.
        asset_type: "stock" or "crypto".

    Returns
    -------
    dict with: score, regime, pcr, iv_skew, avg_call_iv, avg_put_iv, confidence
    """
    if asset_type == "crypto":
        return dict(_NEUTRAL_OPTIONS)

    clean = symbol.split("/")[0].upper()
    now = time.monotonic()

    entry = _cache.get(clean)
    if entry is not None and now < entry.get("expires_at", 0):
        return {k: v for k, v in entry.items() if k != "expires_at"}

    raw = _fetch_options_data(clean)
    if not raw:
        logger.debug("Options signal: no data for %s", clean)
        return dict(_NEUTRAL_OPTIONS)

    pcr      = raw.get("pcr")
    iv_skew  = raw.get("iv_skew")
    conf_vol = raw.get("confidence_vol", 0.35)

    pcr_score  = _score_pcr(pcr)      if pcr is not None  else 0.0
    skew_score = _score_iv_skew(iv_skew) if iv_skew is not None else 0.0

    composite = float(np.clip(pcr_score + skew_score, -0.40, 0.40))
    regime    = _classify_regime(composite)

    result = {
        "score":       round(composite, 4),
        "regime":      regime,
        "pcr":         pcr,
        "iv_skew":     iv_skew,
        "avg_call_iv": raw.get("avg_call_iv"),
        "avg_put_iv":  raw.get("avg_put_iv"),
        "confidence":  round(conf_vol, 4),
    }

    _cache[clean] = {**result, "expires_at": now + _CACHE_TTL}

    logger.debug(
        "Options signal %s: pcr=%.2f skew=%s score=%.3f regime=%s",
        clean, pcr or 0,
        f"{iv_skew:.2f}" if iv_skew else "N/A",
        composite, regime,
    )
    return result
