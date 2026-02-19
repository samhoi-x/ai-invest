"""Signal accuracy tracker: verify historical signals against actual price moves."""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from db.database import get_db
from data.stock_fetcher import fetch_stock_data
from data.crypto_fetcher import fetch_crypto_data

logger = logging.getLogger(__name__)


def get_unchecked_signals(min_age_days: int = 5) -> list[dict]:
    """Get signals old enough to evaluate but not yet checked."""
    cutoff = (datetime.utcnow() - timedelta(days=min_age_days)).isoformat()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, symbol, direction, strength, confidence,
                   technical_score, sentiment_score, ml_score,
                   signal_type, created_at
            FROM signals
            WHERE outcome_checked_at IS NULL
              AND created_at <= ?
            ORDER BY created_at
            LIMIT 100
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def evaluate_signal(signal: dict) -> dict | None:
    """Check if a signal's prediction was correct.

    Returns dict with outcome data, or None if price data unavailable.
    """
    symbol = signal["symbol"]
    created = signal["created_at"]
    direction = signal["direction"]

    try:
        signal_date = pd.Timestamp(created)
    except Exception:
        logger.warning("Could not parse signal date '%s' for signal %s", created, signal.get("id"))
        return None

    # Fetch enough data to cover the signal date plus 10 forward trading days.
    # Signals may be queued for weeks before being evaluated, so derive the
    # required lookback from the actual signal age rather than using a fixed window.
    signal_age_days = max(0, (datetime.utcnow() - signal_date.to_pydatetime().replace(tzinfo=None)).days)
    fetch_days = signal_age_days + 20  # signal age + buffer for 10 trading days forward

    try:
        if "/" in symbol:
            df = fetch_crypto_data(symbol, days=fetch_days)
        else:
            # yfinance period strings: approximate calendar days → nearest valid period
            if fetch_days <= 30:
                period = "1mo"
            elif fetch_days <= 90:
                period = "3mo"
            elif fetch_days <= 180:
                period = "6mo"
            else:
                period = "1y"
            df = fetch_stock_data(symbol, period=period)
    except Exception:
        logger.warning("Failed to fetch price data for %s during accuracy evaluation", symbol)
        return None

    if df is None or df.empty:
        return None

    # Find signal date price
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)  # convert to UTC then drop tz

    # Find closest trading day on or after signal date
    mask = df.index >= signal_date.normalize()
    if mask.sum() == 0:
        return None

    base_idx = df.index[mask][0]
    base_price = df.loc[base_idx, "close"]

    if base_price == 0:
        return None

    # 5-day and 10-day forward returns
    future_dates = df.index[df.index > base_idx]

    return_5d = None
    return_10d = None

    if len(future_dates) >= 5:
        price_5d = df.loc[future_dates[4], "close"]
        return_5d = (price_5d / base_price) - 1

    if len(future_dates) >= 10:
        price_10d = df.loc[future_dates[9], "close"]
        return_10d = (price_10d / base_price) - 1

    # Determine if signal was correct (using 5-day return)
    correct = None
    if return_5d is not None:
        if direction == "BUY":
            correct = 1 if return_5d > 0 else 0
        elif direction == "SELL":
            correct = 1 if return_5d < 0 else 0
        else:  # HOLD
            correct = 1 if abs(return_5d) < 0.02 else 0  # Within 2%

    return {
        "return_5d": round(return_5d, 6) if return_5d is not None else None,
        "return_10d": round(return_10d, 6) if return_10d is not None else None,
        "correct": correct,
    }


def update_signal_outcome(signal_id: int, outcome: dict):
    """Write outcome data back to the signals table."""
    with get_db() as conn:
        conn.execute("""
            UPDATE signals SET
                outcome_return_5d = ?,
                outcome_return_10d = ?,
                outcome_correct = ?,
                outcome_checked_at = datetime('now')
            WHERE id = ?
        """, (outcome["return_5d"], outcome["return_10d"],
              outcome["correct"], signal_id))


def run_accuracy_check() -> dict:
    """Check all pending signals and return summary stats."""
    unchecked = get_unchecked_signals()
    checked = 0
    correct = 0
    total_evaluated = 0

    for sig in unchecked:
        outcome = evaluate_signal(sig)
        if outcome is None:
            continue
        update_signal_outcome(sig["id"], outcome)
        checked += 1
        if outcome["correct"] is not None:
            total_evaluated += 1
            correct += outcome["correct"]

    accuracy = correct / total_evaluated if total_evaluated > 0 else 0

    return {
        "checked": checked,
        "total_evaluated": total_evaluated,
        "correct": correct,
        "accuracy": round(accuracy, 4),
    }


def get_accuracy_stats() -> dict:
    """Get overall accuracy statistics from evaluated signals."""
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE outcome_correct IS NOT NULL"
        ).fetchone()[0]
        correct = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE outcome_correct = 1"
        ).fetchone()[0]

        # By direction
        stats_by_dir = {}
        for direction in ("BUY", "SELL", "HOLD"):
            row = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN outcome_correct = 1 THEN 1 ELSE 0 END) as correct,
                       AVG(outcome_return_5d) as avg_return_5d
                FROM signals
                WHERE outcome_correct IS NOT NULL AND direction = ?
            """, (direction,)).fetchone()
            stats_by_dir[direction] = {
                "total": row[0],
                "correct": row[1] or 0,
                "accuracy": round((row[1] or 0) / row[0], 4) if row[0] > 0 else 0,
                "avg_return_5d": round(row[2] or 0, 6),
            }

        # By factor (avg scores for correct vs incorrect)
        factor_stats = conn.execute("""
            SELECT outcome_correct,
                   AVG(technical_score) as avg_tech,
                   AVG(sentiment_score) as avg_sent,
                   AVG(ml_score) as avg_ml
            FROM signals
            WHERE outcome_correct IS NOT NULL
            GROUP BY outcome_correct
        """).fetchall()
        factor_data = {}
        for row in factor_stats:
            label = "correct" if row[0] == 1 else "incorrect"
            factor_data[label] = {
                "avg_technical": round(row[1] or 0, 4),
                "avg_sentiment": round(row[2] or 0, 4),
                "avg_ml": round(row[3] or 0, 4),
            }

    return {
        "total_evaluated": total,
        "correct": correct,
        "overall_accuracy": round(correct / total, 4) if total > 0 else 0,
        "by_direction": stats_by_dir,
        "by_factor": factor_data,
    }


def compute_adaptive_weights(min_samples: int = 30) -> dict:
    """Estimate per-factor weights from historical signal outcomes.

    Method: for each factor, compute the point-biserial correlation between
    (direction-signed factor score) and outcome_correct.  Factors with higher
    positive correlation get proportionally more weight.  The result is blended
    50/50 with the config priors so weights shift gradually and never collapse
    to zero.  Falls back to config defaults when there are fewer than
    ``min_samples`` evaluated non-HOLD signals.

    Returns:
        dict with keys 'technical', 'sentiment', 'ml' that sum to 1.0.
    """
    from config import SIGNAL_WEIGHTS

    with get_db() as conn:
        rows = conn.execute("""
            SELECT technical_score, sentiment_score, ml_score,
                   direction, outcome_correct
            FROM signals
            WHERE outcome_correct IS NOT NULL
              AND direction != 'HOLD'
        """).fetchall()

    if len(rows) < min_samples:
        logger.debug(
            "compute_adaptive_weights: only %d samples (need %d), using config defaults",
            len(rows), min_samples,
        )
        return dict(SIGNAL_WEIGHTS)

    tech_scores = np.array([r["technical_score"] or 0.0 for r in rows])
    sent_scores = np.array([r["sentiment_score"] or 0.0 for r in rows])
    ml_scores   = np.array([r["ml_score"]        or 0.0 for r in rows])
    correct     = np.array([r["outcome_correct"]         for r in rows], dtype=float)

    # Sign-adjust factor scores so that a BUY signal with positive score counts
    # as "aligned" and a SELL signal with negative score also counts as "aligned".
    dir_sign = np.array([1.0 if r["direction"] == "BUY" else -1.0 for r in rows])
    tech_aligned = tech_scores * dir_sign
    sent_aligned = sent_scores * dir_sign
    ml_aligned   = ml_scores   * dir_sign

    def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
        """Point-biserial correlation, floored at 0 (only reward, no punishment)."""
        if x.std() < 1e-9:
            return 0.0
        return float(max(0.0, np.corrcoef(x, y)[0, 1]))

    tech_corr = _safe_corr(tech_aligned, correct)
    sent_corr = _safe_corr(sent_aligned, correct)
    ml_corr   = _safe_corr(ml_aligned,   correct)

    total_corr = tech_corr + sent_corr + ml_corr

    if total_corr < 1e-9:
        # All correlations are zero or negative — stay with config defaults.
        logger.debug("compute_adaptive_weights: no positive correlations found, using defaults")
        return dict(SIGNAL_WEIGHTS)

    data_w = {
        "technical": tech_corr / total_corr,
        "sentiment": sent_corr / total_corr,
        "ml":        ml_corr   / total_corr,
        "macro":     0.0,   # not data-driven; macro is global, not per-symbol
    }

    # Bayesian shrinkage: 50 % data-driven, 50 % config prior
    blended = {
        "technical": 0.5 * data_w["technical"] + 0.5 * SIGNAL_WEIGHTS["technical"],
        "sentiment": 0.5 * data_w["sentiment"] + 0.5 * SIGNAL_WEIGHTS["sentiment"],
        "ml":        0.5 * data_w["ml"]        + 0.5 * SIGNAL_WEIGHTS["ml"],
        "macro":     SIGNAL_WEIGHTS["macro"],   # always held at config prior
    }

    # Re-normalise to guarantee weights sum to exactly 1.0
    total = sum(blended.values())
    result = {k: round(v / total, 4) for k, v in blended.items()}

    logger.info(
        "Adaptive weights (n=%d): tech=%.3f sent=%.3f ml=%.3f macro=%.3f "
        "(corr: tech=%.3f sent=%.3f ml=%.3f)",
        len(rows),
        result["technical"], result["sentiment"], result["ml"], result["macro"],
        tech_corr, sent_corr, ml_corr,
    )
    return result
