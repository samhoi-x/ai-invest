"""Chart pattern recognition — detects classic technical formations.

Patterns detected
-----------------
Bullish patterns (positive score):
  Double Bottom     Two troughs at similar level with peak between  +0.20
  Inv Head&Shoulders Three troughs, centre deepest                  +0.25
  Bull Flag         Strong up-move then tight pullback, breakout    +0.15
  Consolidation Up  Tight range followed by upward breakout         +0.15

Bearish patterns (negative score):
  Double Top        Two peaks at similar level with valley between  -0.20
  Head & Shoulders  Three peaks, centre highest                     -0.25
  Bear Flag         Strong down-move then tight bounce, breakdown   -0.15
  Consolidation Dn  Tight range followed by downward breakout       -0.15

Scoring
-------
All individual pattern scores are clipped to [-0.40, +0.40].
When multiple patterns are detected the scores are summed then clipped
to [-1.0, +1.0].  Confidence = min(1, 0.3 + 0.15 * n_patterns).

Public API
----------
detect_patterns(df, lookback=120) -> dict
    score      float   Composite pattern score (-1 to +1)
    confidence float   0.0–1.0
    patterns   list[dict]  Each detected pattern: {name, type, score, bar, detail}
    n_patterns int     Number of patterns found
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Peak / trough detection ───────────────────────────────────────────────────

def _deduplicate_extrema(indices: list[int], arr: np.ndarray,
                         order: int, keep: str = "min") -> list[int]:
    """Merge nearby extrema (within `order` bars) keeping the best per cluster.

    Prevents two bars at the same price level (e.g. linspace endpoint repeats
    or flat-top candles) from being counted as two separate peaks/troughs.
    """
    if not indices:
        return []
    result: list[int] = []
    cluster = [indices[0]]
    for idx in indices[1:]:
        if idx - cluster[-1] <= order:
            cluster.append(idx)
        else:
            best = (min if keep == "min" else max)(cluster, key=lambda i: arr[i])
            result.append(best)
            cluster = [idx]
    best = (min if keep == "min" else max)(cluster, key=lambda i: arr[i])
    result.append(best)
    return result


def _local_peaks(arr: np.ndarray, order: int = 5) -> list[int]:
    """Indices of local maxima in arr.

    A bar at index i is a peak if it equals the maximum of the window
    [i-order, i+order] AND is not lower than either immediate neighbour
    AND at least one immediate neighbour is strictly lower (avoids flat
    plateaus producing many spurious peaks).
    """
    peaks = []
    n = len(arr)
    for i in range(order, n - order):
        window = arr[max(0, i - order): i + order + 1]
        if arr[i] < np.max(window):
            continue
        left_ok  = arr[i] >= arr[i - 1]
        right_ok = arr[i] >= arr[i + 1]
        strict   = arr[i] > arr[i - 1] or arr[i] > arr[i + 1]
        if left_ok and right_ok and strict:
            peaks.append(i)
    return peaks


def _local_troughs(arr: np.ndarray, order: int = 5) -> list[int]:
    """Indices of local minima.

    A bar at index i is a trough if it equals the minimum of the window
    [i-order, i+order] AND is not greater than either immediate neighbour
    AND at least one immediate neighbour is strictly higher.
    """
    troughs = []
    n = len(arr)
    for i in range(order, n - order):
        window = arr[max(0, i - order): i + order + 1]
        if arr[i] > np.min(window):
            continue
        left_ok  = arr[i] <= arr[i - 1]
        right_ok = arr[i] <= arr[i + 1]
        strict   = arr[i] < arr[i - 1] or arr[i] < arr[i + 1]
        if left_ok and right_ok and strict:
            troughs.append(i)
    return troughs


# ── Individual pattern detectors ──────────────────────────────────────────────

def _double_top(prices: np.ndarray, peaks: list[int],
                tol: float = 0.03) -> Optional[dict]:
    """Last two peaks at similar height with a valley in between → bearish."""
    if len(peaks) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    h1, h2 = prices[p1], prices[p2]
    if h1 <= 0 or h2 <= 0:
        return None
    if abs(h1 - h2) / max(h1, h2) > tol:
        return None
    valley = np.min(prices[p1: p2 + 1])
    depth = (min(h1, h2) - valley) / min(h1, h2)
    if depth < 0.03:
        return None
    # Confirm: price declining from second peak
    if len(prices) > p2 + 2 and prices[-1] >= h2 * 0.99:
        return None
    score = -0.20 - min(0.10, depth * 0.5)
    return {"name": "Double Top", "type": "bearish",
            "score": round(score, 3), "bar": p2,
            "detail": f"peaks≈{h1:.2f}/{h2:.2f}, depth={depth*100:.1f}%"}


def _double_bottom(prices: np.ndarray, troughs: list[int],
                   tol: float = 0.03) -> Optional[dict]:
    """Last two troughs at similar depth with a peak in between → bullish."""
    if len(troughs) < 2:
        return None
    t1, t2 = troughs[-2], troughs[-1]
    lo1, lo2 = prices[t1], prices[t2]
    if lo1 <= 0 or lo2 <= 0:
        return None
    if abs(lo1 - lo2) / max(lo1, lo2) > tol:
        return None
    peak = np.max(prices[t1: t2 + 1])
    rise = (peak - max(lo1, lo2)) / max(lo1, lo2)
    if rise < 0.03:
        return None
    # Confirm: price rising after second trough
    if len(prices) > t2 + 2 and prices[-1] <= lo2 * 1.01:
        return None
    score = 0.20 + min(0.10, rise * 0.5)
    return {"name": "Double Bottom", "type": "bullish",
            "score": round(score, 3), "bar": t2,
            "detail": f"troughs≈{lo1:.2f}/{lo2:.2f}, rise={rise*100:.1f}%"}


def _head_and_shoulders(prices: np.ndarray, peaks: list[int],
                        tol: float = 0.05) -> Optional[dict]:
    """Three peaks: left shoulder, head (tallest), right shoulder → bearish."""
    if len(peaks) < 3:
        return None
    ls, hd, rs = peaks[-3], peaks[-2], peaks[-1]
    h_ls, h_hd, h_rs = prices[ls], prices[hd], prices[rs]
    if h_hd <= 0:
        return None
    # Head must be the tallest
    if not (h_hd > h_ls and h_hd > h_rs):
        return None
    # Shoulders roughly similar height
    if abs(h_ls - h_rs) / max(h_ls, h_rs) > tol:
        return None
    # Neckline
    nk1 = np.min(prices[ls: hd + 1])
    nk2 = np.min(prices[hd: rs + 1])
    neckline = (nk1 + nk2) / 2
    # Price near or below neckline confirms pattern
    if prices[-1] > neckline * 1.03:
        return None
    depth = (h_hd - neckline) / h_hd
    score = -0.25 - min(0.10, depth * 0.3)
    return {"name": "Head & Shoulders", "type": "bearish",
            "score": round(score, 3), "bar": rs,
            "detail": f"head={h_hd:.2f}, neckline={neckline:.2f}"}


def _inv_head_and_shoulders(prices: np.ndarray, troughs: list[int],
                             tol: float = 0.05) -> Optional[dict]:
    """Three troughs: left shoulder, head (deepest), right shoulder → bullish."""
    if len(troughs) < 3:
        return None
    ls, hd, rs = troughs[-3], troughs[-2], troughs[-1]
    lo_ls, lo_hd, lo_rs = prices[ls], prices[hd], prices[rs]
    if lo_hd <= 0:
        return None
    # Head must be deepest
    if not (lo_hd < lo_ls and lo_hd < lo_rs):
        return None
    # Shoulders roughly similar
    if abs(lo_ls - lo_rs) / max(lo_ls, lo_rs) > tol:
        return None
    # Neckline
    nk1 = np.max(prices[ls: hd + 1])
    nk2 = np.max(prices[hd: rs + 1])
    neckline = (nk1 + nk2) / 2
    # Price near or above neckline confirms
    if prices[-1] < neckline * 0.97:
        return None
    rise = (neckline - lo_hd) / neckline
    score = 0.25 + min(0.10, rise * 0.3)
    return {"name": "Inv Head & Shoulders", "type": "bullish",
            "score": round(score, 3), "bar": rs,
            "detail": f"head={lo_hd:.2f}, neckline={neckline:.2f}"}


def _bull_flag(prices: np.ndarray, window: int = 60,
               flag_bars: int = 15) -> Optional[dict]:
    """Strong upward pole + tight consolidation + upward breakout → bullish."""
    if len(prices) < window + flag_bars:
        return None
    pole = prices[-(window + flag_bars): -flag_bars]
    flag = prices[-flag_bars:]
    pole_return = (pole[-1] / pole[0]) - 1
    if pole_return < 0.08:          # Pole must be at least +8%
        return None
    flag_range = (np.max(flag) - np.min(flag)) / np.mean(flag)
    if flag_range > 0.06:           # Tight channel: ≤ 6% range
        return None
    # Breakout: last close above flag high
    if flag[-1] < np.max(flag) * 0.98:
        return None
    return {"name": "Bull Flag", "type": "bullish",
            "score": 0.15, "bar": len(prices) - 1,
            "detail": f"pole={pole_return*100:.1f}%, flag_range={flag_range*100:.1f}%"}


def _bear_flag(prices: np.ndarray, window: int = 60,
               flag_bars: int = 15) -> Optional[dict]:
    """Strong downward pole + tight bounce + downward breakdown → bearish."""
    if len(prices) < window + flag_bars:
        return None
    pole = prices[-(window + flag_bars): -flag_bars]
    flag = prices[-flag_bars:]
    pole_return = (pole[-1] / pole[0]) - 1
    if pole_return > -0.08:         # Pole must be at least -8%
        return None
    flag_range = (np.max(flag) - np.min(flag)) / np.mean(flag)
    if flag_range > 0.06:
        return None
    # Breakdown: last close below flag low
    if flag[-1] > np.min(flag) * 1.02:
        return None
    return {"name": "Bear Flag", "type": "bearish",
            "score": -0.15, "bar": len(prices) - 1,
            "detail": f"pole={pole_return*100:.1f}%, flag_range={flag_range*100:.1f}%"}


def _consolidation_breakout(prices: np.ndarray,
                             consol_bars: int = 20,
                             breakout_bars: int = 5) -> Optional[dict]:
    """Tight range (≤5%) followed by directional breakout in last N bars."""
    if len(prices) < consol_bars + breakout_bars:
        return None
    consol = prices[-(consol_bars + breakout_bars): -breakout_bars]
    recent = prices[-breakout_bars:]
    rng = (np.max(consol) - np.min(consol)) / np.mean(consol)
    if rng > 0.05:                  # Must be tight range
        return None
    consol_high = np.max(consol)
    consol_low  = np.min(consol)
    last = recent[-1]
    if last > consol_high * 1.02:   # Upward breakout
        move = (last - consol_high) / consol_high
        return {"name": "Consolidation Breakout Up", "type": "bullish",
                "score": min(0.20, 0.10 + move * 2), "bar": len(prices) - 1,
                "detail": f"range={rng*100:.1f}%, breakout={move*100:.1f}%"}
    elif last < consol_low * 0.98:  # Downward breakdown
        move = (consol_low - last) / consol_low
        return {"name": "Consolidation Breakout Dn", "type": "bearish",
                "score": -min(0.20, 0.10 + move * 2), "bar": len(prices) - 1,
                "detail": f"range={rng*100:.1f}%, breakdown={move*100:.1f}%"}
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def detect_patterns(df: pd.DataFrame, lookback: int = 120) -> dict:
    """Scan a price DataFrame for classic chart patterns.

    Args:
        df:       OHLCV DataFrame with at least a 'close' column.
        lookback: Number of recent bars to analyse (default 120 ≈ 6 months daily).

    Returns
    -------
    dict with:
        score      float   Composite score (-1 to +1)
        confidence float   0.0–1.0
        patterns   list    Each: {name, type, score, bar, detail}
        n_patterns int
    """
    _neutral = {"score": 0.0, "confidence": 0.0, "patterns": [], "n_patterns": 0}

    try:
        if df is None or df.empty or "close" not in df.columns:
            return _neutral

        closes = df["close"].dropna()
        if len(closes) < 40:
            return _neutral

        prices = closes.iloc[-lookback:].to_numpy(dtype=float)
        n = len(prices)

        _order  = max(3, n // 25)
        peaks   = _deduplicate_extrema(_local_peaks(prices, _order),   prices, _order, keep="max")
        troughs = _deduplicate_extrema(_local_troughs(prices, _order), prices, _order, keep="min")

        found: list[dict] = []

        for detector in [
            lambda: _double_top(prices, peaks),
            lambda: _double_bottom(prices, troughs),
            lambda: _head_and_shoulders(prices, peaks),
            lambda: _inv_head_and_shoulders(prices, troughs),
            lambda: _bull_flag(prices),
            lambda: _bear_flag(prices),
            lambda: _consolidation_breakout(prices),
        ]:
            try:
                result = detector()
                if result is not None:
                    found.append(result)
            except Exception as exc:
                logger.debug("Pattern detector error: %s", exc)

        if not found:
            return _neutral

        total_score = float(np.clip(sum(p["score"] for p in found), -1.0, 1.0))
        confidence  = min(1.0, 0.30 + 0.15 * len(found))

        logger.debug(
            "Patterns detected: %s → composite=%.3f conf=%.2f",
            [p["name"] for p in found], total_score, confidence,
        )
        return {
            "score":      round(total_score, 4),
            "confidence": round(confidence, 4),
            "patterns":   found,
            "n_patterns": len(found),
        }

    except Exception as exc:
        logger.warning("detect_patterns failed: %s", exc)
        return _neutral
