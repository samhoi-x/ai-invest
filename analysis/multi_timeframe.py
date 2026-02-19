"""Multi-timeframe confluence analysis.

Evaluates trend alignment across four timeframes to boost signal reliability.
When all timeframes agree, confidence increases; when they conflict, it falls.

Timeframe weights
-----------------
1W  30% – long-term structural trend
1D  40% – primary signal timeframe (matches scheduler data)
4H  20% – intermediate confirmation
1H  10% – entry timing

Public API
----------
compute_mtf_signal(symbol, asset_type, daily_df) -> dict
"""

import logging
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Per-symbol intraday cache (refresh every 2 hours to avoid rate-limit hammering)
_intraday_cache: dict = {}   # {symbol: (df, expires_at)}
_INTRADAY_TTL = 7200         # seconds

TF_WEIGHTS = {"1W": 0.30, "1D": 0.40, "4H": 0.20, "1H": 0.10}


# ── Resamplers ────────────────────────────────────────────────────────────────

def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample an OHLCV DataFrame to the given pandas offset alias."""
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    resampled = df.resample(rule).agg(agg).dropna(subset=["close"])
    return resampled


# ── Intraday data fetch (stocks only) ─────────────────────────────────────────

def _fetch_intraday_stock(symbol: str) -> pd.DataFrame:
    """Fetch 1-hour bars for a stock ticker (last 60 days, cached 2 h)."""
    now = time.monotonic()
    if symbol in _intraday_cache:
        cached_df, expires_at = _intraday_cache[symbol]
        if now < expires_at:
            return cached_df

    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        raw = ticker.history(period="60d", interval="1h")
        if raw is None or raw.empty:
            df = pd.DataFrame()
        else:
            raw.index = pd.to_datetime(raw.index)
            if raw.index.tz is not None:
                raw.index = raw.index.tz_convert(None)
            df = raw.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = df[["open", "high", "low", "close", "volume"]].dropna()
    except Exception as exc:
        logger.debug("MTF: intraday fetch failed for %s: %s", symbol, exc)
        df = pd.DataFrame()

    _intraday_cache[symbol] = (df, now + _INTRADAY_TTL)
    return df


# ── MTF signal ────────────────────────────────────────────────────────────────

def compute_mtf_signal(symbol: str, asset_type: str,
                       daily_df: pd.DataFrame) -> dict:
    """Compute multi-timeframe confluence signal.

    Parameters
    ----------
    symbol     : ticker string
    asset_type : 'stock' or 'crypto'
    daily_df   : existing daily OHLCV DataFrame (already fetched by scheduler)

    Returns
    -------
    dict with keys:
        score               float  -1 to +1  (TF-weighted composite)
        confidence          float   0 to 1
        alignment           float   0 to 1  (fraction of TFs agreeing)
        tf_scores           dict   {TF: {score, confidence}}
        timeframes_available list[str]
    """
    from analysis.technical import compute_technical_signal

    tf_results: dict = {}

    # ── 1D (always available) ──────────────────────────────────────────
    if daily_df is not None and not daily_df.empty and len(daily_df) >= 30:
        try:
            tf_results["1D"] = compute_technical_signal(daily_df)
        except Exception as exc:
            logger.debug("MTF 1D failed for %s: %s", symbol, exc)

    # ── 1W (resample from daily) ───────────────────────────────────────
    if daily_df is not None and not daily_df.empty and len(daily_df) >= 30:
        try:
            daily_df.index = pd.to_datetime(daily_df.index)
            weekly = _resample_ohlcv(daily_df, "W")
            if len(weekly) >= 15:
                tf_results["1W"] = compute_technical_signal(weekly)
        except Exception as exc:
            logger.debug("MTF 1W failed for %s: %s", symbol, exc)

    # ── Intraday (stocks only) ─────────────────────────────────────────
    if asset_type == "stock":
        try:
            intraday = _fetch_intraday_stock(symbol)
            if not intraday.empty:
                # 1H
                if len(intraday) >= 26:
                    tf_results["1H"] = compute_technical_signal(intraday)
                # 4H (resample from 1H)
                intraday.index = pd.to_datetime(intraday.index)
                four_h = _resample_ohlcv(intraday, "4h")
                if len(four_h) >= 20:
                    tf_results["4H"] = compute_technical_signal(four_h)
        except Exception as exc:
            logger.debug("MTF intraday failed for %s: %s", symbol, exc)

    # ── Bail out if no data ────────────────────────────────────────────
    if not tf_results:
        return {
            "score": 0.0,
            "confidence": 0.0,
            "alignment": 0.5,
            "tf_scores": {},
            "timeframes_available": [],
        }

    # ── Weighted composite score ───────────────────────────────────────
    total_weight = 0.0
    weighted_score = 0.0
    tf_scores: dict = {}

    for tf, sig in tf_results.items():
        w = TF_WEIGHTS.get(tf, 0.15)
        weighted_score += w * sig["score"]
        total_weight += w
        tf_scores[tf] = {
            "score": round(sig["score"], 4),
            "confidence": round(sig["confidence"], 4),
        }

    composite = weighted_score / total_weight if total_weight > 0 else 0.0

    # ── Alignment: fraction of TFs agreeing on the dominant direction ──
    scores_list = [s["score"] for s in tf_results.values()]
    directions = [1 if s > 0.05 else -1 if s < -0.05 else 0 for s in scores_list]
    non_neutral = [d for d in directions if d != 0]

    if non_neutral:
        dominant = max(set(non_neutral), key=non_neutral.count)
        # alignment = proportion of ALL timeframes (incl. neutral) in dominant dir
        alignment = non_neutral.count(dominant) / len(directions)
    else:
        alignment = 0.5  # all neutral — no conviction

    # ── Confidence: avg per-TF confidence scaled by alignment ─────────
    avg_conf = sum(s["confidence"] for s in tf_results.values()) / len(tf_results)
    confidence = float(np.clip(avg_conf * (0.5 + 0.5 * alignment), 0.0, 1.0))

    logger.debug(
        "MTF %s: score=%.3f alignment=%.2f TFs=%s",
        symbol, composite, alignment, list(tf_results.keys()),
    )

    return {
        "score": round(float(np.clip(composite, -1.0, 1.0)), 4),
        "confidence": round(confidence, 4),
        "alignment": round(alignment, 4),
        "tf_scores": tf_scores,
        "timeframes_available": list(tf_results.keys()),
    }
