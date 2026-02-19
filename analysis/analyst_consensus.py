"""Analyst consensus and price target tracker.

Aggregates Wall Street analyst ratings and price targets from yfinance.
When analyst consensus aligns with our signal, confidence increases.

Score computation
-----------------
Uses recommendations_summary (period totals) when available:
  score = (strongBuy×1 + buy×0.5 + hold×0 + sell×(-0.5) + strongSell×(-1)) / total

Falls back to individual recommendations (last 90 days) with text-grade mapping.

Recent upgrade/downgrade bonus: +0.05 per upgrade, -0.05 per downgrade in last 30d.

Integration in signal_combiner
-------------------------------
Blended into sentiment: s_score_adj = 0.70 × original + 0.30 × analyst_score
Boosts confidence ±0.05 when analyst strongly agrees with composite direction.

Public API
----------
get_analyst_consensus(symbol) -> dict    (24-hour cached per symbol)
"""

import logging
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Per-symbol cache { symbol: (result, expires_at) }
_cache: dict = {}
_CACHE_TTL = 24 * 3600   # 24 hours

# Grade → numeric score (-1 to +1)
_GRADE_SCORE: dict[str, float] = {
    "strong buy":      1.0,
    "buy":             0.7,
    "outperform":      0.5,
    "overweight":      0.5,
    "market outperform": 0.5,
    "positive":        0.3,
    "sector outperform": 0.3,
    "neutral":         0.0,
    "hold":            0.0,
    "market perform":  0.0,
    "equal-weight":    0.0,
    "equal weight":    0.0,
    "sector weight":   0.0,
    "sector perform":  0.0,
    "in-line":         0.0,
    "negative":       -0.3,
    "sector underperform": -0.3,
    "underperform":   -0.5,
    "underweight":    -0.5,
    "market underperform": -0.5,
    "sell":           -0.7,
    "strong sell":    -1.0,
}


def _grade_to_score(grade: str) -> Optional[float]:
    return _GRADE_SCORE.get(str(grade).lower().strip())


def _no_consensus() -> dict:
    return {
        "score": 0.0,
        "rating_label": "N/A",
        "total_ratings": 0,
        "buy_pct": None,
        "hold_pct": None,
        "sell_pct": None,
        "recent_upgrades": 0,
        "recent_downgrades": 0,
        "target_price": None,
        "target_upside_pct": None,
        "source": "none",
    }


def _from_recommendations_summary(rec_summary) -> Optional[dict]:
    """Parse the aggregated summary DataFrame (yfinance 0.2.x+)."""
    try:
        if rec_summary is None or rec_summary.empty:
            return None
        # Use the most recent period row
        row = rec_summary.iloc[0]
        strong_buy  = int(row.get("strongBuy",  0) or 0)
        buy         = int(row.get("buy",        0) or 0)
        hold        = int(row.get("hold",       0) or 0)
        sell        = int(row.get("sell",       0) or 0)
        strong_sell = int(row.get("strongSell", 0) or 0)
        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return None
        score = (strong_buy * 1.0 + buy * 0.5 +
                 sell * (-0.5) + strong_sell * (-1.0)) / total
        buy_pct  = (strong_buy + buy) / total
        sell_pct = (sell + strong_sell) / total
        hold_pct = hold / total

        if score > 0.4:
            label = "Strong Buy"
        elif score > 0.1:
            label = "Buy"
        elif score > -0.1:
            label = "Hold"
        elif score > -0.4:
            label = "Sell"
        else:
            label = "Strong Sell"

        return {
            "score": round(float(np.clip(score, -1, 1)), 4),
            "rating_label": label,
            "total_ratings": total,
            "buy_pct":  round(buy_pct,  4),
            "hold_pct": round(hold_pct, 4),
            "sell_pct": round(sell_pct, 4),
            "source": "summary",
        }
    except Exception as exc:
        logger.debug("recommendations_summary parse failed: %s", exc)
        return None


def _from_recommendations_history(recs) -> Optional[dict]:
    """Parse individual analyst recommendation rows (last 90 days)."""
    try:
        if recs is None or recs.empty:
            return None
        recs = recs.copy()
        recs.index = pd.to_datetime(recs.index)
        if recs.index.tz is not None:
            recs.index = recs.index.tz_convert(None)
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
        recent = recs[recs.index >= cutoff]
        if recent.empty:
            return None

        col = "To Grade" if "To Grade" in recent.columns else (
              "toGrade"  if "toGrade"  in recent.columns else None)
        if col is None:
            return None

        scores = []
        for grade in recent[col].dropna():
            s = _grade_to_score(str(grade))
            if s is not None:
                scores.append(s)
        if not scores:
            return None

        score = float(np.mean(scores))
        buys  = sum(1 for s in scores if s > 0.1)
        holds = sum(1 for s in scores if -0.1 <= s <= 0.1)
        sells = sum(1 for s in scores if s < -0.1)
        total = len(scores)

        if score > 0.4:
            label = "Strong Buy"
        elif score > 0.1:
            label = "Buy"
        elif score > -0.1:
            label = "Hold"
        elif score > -0.4:
            label = "Sell"
        else:
            label = "Strong Sell"

        return {
            "score": round(float(np.clip(score, -1, 1)), 4),
            "rating_label": label,
            "total_ratings": total,
            "buy_pct":  round(buys  / total, 4),
            "hold_pct": round(holds / total, 4),
            "sell_pct": round(sells / total, 4),
            "source": "history",
        }
    except Exception as exc:
        logger.debug("recommendations history parse failed: %s", exc)
        return None


def _count_recent_changes(recs, days: int = 30) -> tuple[int, int]:
    """Count upgrades and downgrades in the last N days."""
    try:
        if recs is None or recs.empty:
            return 0, 0
        recs = recs.copy()
        recs.index = pd.to_datetime(recs.index)
        if recs.index.tz is not None:
            recs.index = recs.index.tz_convert(None)
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        recent = recs[recs.index >= cutoff]
        if recent.empty or "Action" not in recent.columns:
            return 0, 0
        upgrades   = (recent["Action"].str.lower() == "up").sum()
        downgrades = (recent["Action"].str.lower() == "down").sum()
        return int(upgrades), int(downgrades)
    except Exception:
        return 0, 0


def _fetch_consensus(symbol: str) -> dict:
    """Fetch and parse analyst data from yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)

        # ── Ratings ──────────────────────────────────────────────────────
        base = None
        # Try summary first (most reliable in recent yfinance)
        try:
            base = _from_recommendations_summary(
                getattr(ticker, "recommendations_summary", None))
        except Exception:
            pass
        # Fall back to history
        if base is None:
            try:
                base = _from_recommendations_history(ticker.recommendations)
            except Exception:
                pass
        if base is None:
            return _no_consensus()

        # ── Upgrades / Downgrades (last 30 days) ─────────────────────────
        ups, downs = 0, 0
        try:
            ups, downs = _count_recent_changes(ticker.recommendations)
        except Exception:
            pass

        # Apply upgrade/downgrade momentum bonus (±0.05 each, capped at ±0.20)
        bonus = float(np.clip((ups - downs) * 0.05, -0.20, 0.20))
        final_score = float(np.clip(base["score"] + bonus, -1.0, 1.0))

        # ── Price target ──────────────────────────────────────────────────
        target_price    = None
        target_upside   = None
        try:
            targets = getattr(ticker, "analyst_price_targets", None)
            if targets and isinstance(targets, dict):
                mean_target = targets.get("mean") or targets.get("current")
                if mean_target:
                    target_price = round(float(mean_target), 2)
                    # Calculate upside from latest close
                    hist = ticker.history(period="5d")
                    if not hist.empty:
                        current = float(hist["Close"].iloc[-1])
                        if current > 0:
                            target_upside = round((target_price - current) / current * 100, 2)
        except Exception:
            pass

        return {
            "score":            round(final_score, 4),
            "rating_label":     base["rating_label"],
            "total_ratings":    base["total_ratings"],
            "buy_pct":          base["buy_pct"],
            "hold_pct":         base["hold_pct"],
            "sell_pct":         base["sell_pct"],
            "recent_upgrades":  ups,
            "recent_downgrades": downs,
            "target_price":     target_price,
            "target_upside_pct": target_upside,
            "source":           base["source"],
        }

    except Exception as exc:
        logger.warning("Analyst consensus fetch failed for %s: %s", symbol, exc)
        return _no_consensus()


def get_analyst_consensus(symbol: str) -> dict:
    """Return analyst consensus for a stock symbol (24-hour cached).

    Crypto symbols (containing '/') always return the no-op result.

    Parameters
    ----------
    symbol : ticker string (e.g. 'AAPL' or 'BTC/USDT')

    Returns
    -------
    dict with keys:
        score              float  -1 (unanimous sell) to +1 (unanimous buy)
        rating_label       str    'Strong Buy' / 'Buy' / 'Hold' / 'Sell' / 'Strong Sell'
        total_ratings      int
        buy_pct            float | None
        hold_pct           float | None
        sell_pct           float | None
        recent_upgrades    int    last 30 days
        recent_downgrades  int    last 30 days
        target_price       float | None
        target_upside_pct  float | None  (vs current price)
        source             str    'summary' / 'history' / 'none'
    """
    if "/" in symbol:
        return _no_consensus()

    now = time.monotonic()
    if symbol in _cache:
        result, expires_at = _cache[symbol]
        if now < expires_at:
            return result

    result = _fetch_consensus(symbol)
    _cache[symbol] = (result, now + _CACHE_TTL)

    logger.info(
        "Analyst consensus %s: %s score=%.3f ratings=%d "
        "(buy=%.0f%% hold=%.0f%% sell=%.0f%%) target=%s upside=%s%%",
        symbol, result["rating_label"], result["score"], result["total_ratings"],
        (result["buy_pct"] or 0) * 100, (result["hold_pct"] or 0) * 100,
        (result["sell_pct"] or 0) * 100,
        result["target_price"], result["target_upside_pct"],
    )
    return result
