"""Signal accuracy tracker: verify historical signals against actual price moves."""

import logging
from datetime import datetime, timedelta

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

    # Fetch recent data
    try:
        if "/" in symbol:
            df = fetch_crypto_data(symbol, days=30)
        else:
            df = fetch_stock_data(symbol, period="1mo")
    except Exception:
        logger.warning("Failed to fetch price data for %s during accuracy evaluation", symbol)
        return None

    if df is None or df.empty:
        return None

    # Find signal date price
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Find closest trading day on or after signal date
    mask = df.index >= signal_date.normalize()
    if mask.sum() == 0:
        return None

    base_idx = df.index[mask][0]
    base_price = df.loc[base_idx, "close"]

    if base_price == 0:
        return None

    # 5-day and 10-day forward returns
    future_5 = df.index[df.index > base_idx]
    future_10 = df.index[df.index > base_idx]

    return_5d = None
    return_10d = None

    if len(future_5) >= 5:
        price_5d = df.loc[future_5[4], "close"]
        return_5d = (price_5d / base_price) - 1

    if len(future_10) >= 10:
        price_10d = df.loc[future_10[9], "close"]
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
