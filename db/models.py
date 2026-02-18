"""Database helper functions for CRUD operations."""

import json
import logging
from datetime import datetime
from db.database import get_db

logger = logging.getLogger(__name__)


# ── Settings ──────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to decode JSON for setting '%s', returning raw value", key)
                return row["value"]
        return default


def set_setting(key: str, value):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )


# ── Holdings ──────────────────────────────────────────────────────────

def get_holdings():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM holdings ORDER BY symbol").fetchall()]


def upsert_holding(symbol, asset_type, quantity, avg_cost, sector=None):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO holdings (symbol, asset_type, quantity, avg_cost, entry_date, sector)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                quantity=excluded.quantity,
                avg_cost=excluded.avg_cost,
                sector=excluded.sector
        """, (symbol, asset_type, quantity, avg_cost, datetime.now().isoformat(), sector))


def remove_holding(symbol):
    with get_db() as conn:
        conn.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))


# ── Transactions ──────────────────────────────────────────────────────

def add_transaction(symbol, action, quantity, price, note=""):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO transactions (symbol, action, quantity, price, note) VALUES (?, ?, ?, ?, ?)",
            (symbol, action, quantity, price, note),
        )


def get_transactions(limit=100):
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM transactions ORDER BY executed_at DESC LIMIT ?", (limit,)
        ).fetchall()]


# ── Signals ───────────────────────────────────────────────────────────

def save_signal(symbol, signal_type, direction, strength, confidence,
                technical_score=None, sentiment_score=None, ml_score=None):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO signals (symbol, signal_type, direction, strength,
                confidence, technical_score, sentiment_score, ml_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, signal_type, direction, strength, confidence,
              technical_score, sentiment_score, ml_score))


def get_latest_signals(limit=50):
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]


def get_signal_history(symbol, days=90):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT * FROM signals WHERE symbol=?
            AND created_at >= datetime('now', ?)
            ORDER BY created_at
        """, (symbol, f"-{days} days")).fetchall()]


# ── Risk Alerts ───────────────────────────────────────────────────────

def add_risk_alert(alert_type, severity, message, symbol=None):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO risk_alerts (alert_type, severity, message, symbol) VALUES (?, ?, ?, ?)",
            (alert_type, severity, message, symbol),
        )


def get_risk_alerts(limit=50, unacknowledged_only=False):
    with get_db() as conn:
        query = "SELECT * FROM risk_alerts"
        if unacknowledged_only:
            query += " WHERE acknowledged=0"
        query += " ORDER BY created_at DESC LIMIT ?"
        return [dict(r) for r in conn.execute(query, (limit,)).fetchall()]


# ── Backtest Results ──────────────────────────────────────────────────

def save_backtest(name, config, total_return, annual_return, sharpe_ratio,
                  max_drawdown, win_rate, total_trades, equity_curve):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO backtest_results (name, config, total_return, annual_return,
                sharpe_ratio, max_drawdown, win_rate, total_trades, equity_curve)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, json.dumps(config), total_return, annual_return,
              sharpe_ratio, max_drawdown, win_rate, total_trades, json.dumps(equity_curve)))


def get_backtest_results(limit=20):
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]
        for r in rows:
            try:
                r["config"] = json.loads(r["config"]) if r["config"] else {}
            except (json.JSONDecodeError, TypeError):
                r["config"] = {}
            try:
                r["equity_curve"] = json.loads(r["equity_curve"]) if r["equity_curve"] else []
            except (json.JSONDecodeError, TypeError):
                r["equity_curve"] = []
        return rows
