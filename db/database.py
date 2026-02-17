"""SQLite database connection and initialization."""

import logging
import sqlite3
from contextlib import contextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        logger.exception("Database operation failed, rolling back")
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
        -- Price data cache
        CREATE TABLE IF NOT EXISTS price_cache (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL,
            asset_type TEXT DEFAULT 'stock',
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (symbol, date, asset_type)
        );

        -- News cache
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            title TEXT,
            description TEXT,
            source TEXT,
            url TEXT,
            published_at TEXT,
            fetched_at TEXT DEFAULT (datetime('now'))
        );

        -- Sentiment scores
        CREATE TABLE IF NOT EXISTS sentiment_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            score REAL NOT NULL,
            label TEXT,
            text_snippet TEXT,
            computed_at TEXT DEFAULT (datetime('now'))
        );

        -- ML predictions
        CREATE TABLE IF NOT EXISTS ml_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            model_type TEXT NOT NULL,
            prediction REAL NOT NULL,
            confidence REAL,
            predicted_at TEXT DEFAULT (datetime('now')),
            target_date TEXT
        );

        -- Trading signals
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            strength REAL NOT NULL,
            confidence REAL,
            technical_score REAL,
            sentiment_score REAL,
            ml_score REAL,
            created_at TEXT DEFAULT (datetime('now')),
            -- Outcome tracking (filled later by accuracy tracker)
            outcome_return_5d REAL,
            outcome_return_10d REAL,
            outcome_correct INTEGER,
            outcome_checked_at TEXT
        );

        -- Portfolio holdings
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            asset_type TEXT DEFAULT 'stock',
            quantity REAL NOT NULL,
            avg_cost REAL NOT NULL,
            entry_date TEXT,
            stop_loss REAL,
            sector TEXT
        );

        -- Portfolio transactions
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            executed_at TEXT DEFAULT (datetime('now')),
            note TEXT
        );

        -- Backtest results
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            config TEXT,
            total_return REAL,
            annual_return REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            win_rate REAL,
            total_trades INTEGER,
            equity_curve TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- User settings
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- Risk alerts
        CREATE TABLE IF NOT EXISTS risk_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            symbol TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            acknowledged INTEGER DEFAULT 0
        );

        -- Create indexes
        CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_cache(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_cache(symbol);
        """)


# Initialize on import
init_db()
