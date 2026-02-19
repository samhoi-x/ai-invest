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
    # journal_mode=WAL is a persistent database-level setting; set once in
    # init_db() so we avoid the round-trip on every connection.
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
        # Set WAL mode once; it persists at the database file level across
        # all future connections, so there is no need to repeat it per-connection.
        conn.execute("PRAGMA journal_mode=WAL")
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
            macro_score  REAL,
            macro_regime TEXT,
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

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_price_symbol   ON price_cache(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol  ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_news_symbol     ON news_cache(symbol);

        -- Indexes for accuracy_tracker queries
        -- get_unchecked_signals: WHERE outcome_checked_at IS NULL AND created_at <= ?
        CREATE INDEX IF NOT EXISTS idx_signals_unchecked
            ON signals(outcome_checked_at, created_at);
        -- compute_adaptive_weights: WHERE outcome_correct IS NOT NULL AND direction != 'HOLD'
        CREATE INDEX IF NOT EXISTS idx_signals_outcome_dir
            ON signals(outcome_correct, direction);

        -- Paper trading: virtual positions
        CREATE TABLE IF NOT EXISTS paper_positions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,
            entry_date  TEXT    NOT NULL,
            entry_price REAL    NOT NULL,
            quantity    REAL    NOT NULL,
            stop_loss   REAL,
            trailing_stop REAL,
            highest_price REAL,
            status      TEXT    NOT NULL DEFAULT 'open',
            opened_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            closed_at   TEXT,
            close_price REAL,
            realized_pnl REAL   DEFAULT 0
        );

        -- Paper trading: virtual trade log
        CREATE TABLE IF NOT EXISTS paper_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,
            action      TEXT    NOT NULL,
            price       REAL    NOT NULL,
            quantity    REAL    NOT NULL,
            pnl         REAL    DEFAULT 0,
            reason      TEXT,
            executed_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_paper_pos_symbol ON paper_positions(symbol, status);
        CREATE INDEX IF NOT EXISTS idx_paper_trades_sym ON paper_trades(symbol);
        """)


def _migrate_db():
    """Apply schema migrations for columns added after initial release."""
    with get_db() as conn:
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        if "macro_score" not in existing_cols:
            conn.execute("ALTER TABLE signals ADD COLUMN macro_score REAL")
        if "macro_regime" not in existing_cols:
            conn.execute("ALTER TABLE signals ADD COLUMN macro_regime TEXT")


# Initialize on import
init_db()
_migrate_db()
