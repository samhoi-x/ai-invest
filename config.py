"""Global configuration for AI Investment System."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "invest.db"
MODELS_DIR = BASE_DIR / "models"

# ── API Keys ───────────────────────────────────────────────────────────
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "AIInvestBot/1.0")

# ── Default Watchlists ─────────────────────────────────────────────────
DEFAULT_STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "SPY", "QQQ"]
DEFAULT_CRYPTO = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]

# ── Signal Weights (Conservative / 穩健型) ─────────────────────────────
SIGNAL_WEIGHTS = {
    "technical": 0.35,
    "sentiment": 0.25,
    "ml": 0.40,
}

# Signal thresholds (conservative bias)
BUY_THRESHOLD = 0.3
BUY_CONFIDENCE_MIN = 0.65
SELL_THRESHOLD = -0.2
SELL_CONFIDENCE_MIN = 0.50

# ── Risk Management ───────────────────────────────────────────────────
RISK = {
    "max_single_position": 0.15,       # 15% max per position
    "max_crypto_allocation": 0.30,     # 30% max in crypto
    "max_sector_concentration": 0.35,  # 35% max per sector
    "max_trade_risk": 0.01,            # 1% portfolio risk per trade
    "min_cash_reserve": 0.10,          # 10% minimum cash
    "drawdown_warning": 0.08,          # 8% drawdown → warning
    "drawdown_halt": 0.12,             # 12% drawdown → halt new buys
    "drawdown_reduce": 0.15,           # 15% drawdown → reduce 25%
}

# Stop-loss settings
STOP_LOSS = {
    "atr_multiplier": 2.0,            # ATR-based: entry - 2x ATR
    "percentage": 0.05,               # Fixed: 5% below entry
    "trailing": 0.07,                 # Trailing: 7%
}

# ── Technical Analysis ────────────────────────────────────────────────
TECH_PARAMS = {
    "sma_periods": [20, 50, 200],
    "ema_periods": [12, 26],
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bb_period": 20,
    "bb_std": 2,
    "atr_period": 14,
    "stoch_k": 14,
    "stoch_d": 3,
}

# ── ML Model Parameters ──────────────────────────────────────────────
ML_PARAMS = {
    "xgboost_weight": 0.35,
    "lightgbm_weight": 0.30,
    "lstm_weight": 0.35,
    "forward_days": 5,                 # Predict 5-day forward return
    "lstm_window": 60,                 # 60-day sliding window
    "train_window_years": 2,           # Rolling 2-year training
    "retrain_interval_days": 60,       # Retrain every 60 days
}

# ── Cache Settings ────────────────────────────────────────────────────
CACHE_TTL = {
    "price_minutes": 15,               # Price data cache: 15 min
    "news_minutes": 30,                # News cache: 30 min
    "sentiment_minutes": 60,           # Sentiment cache: 1 hour
    "ml_prediction_minutes": 120,      # ML predictions cache: 2 hours
}

# ── UI Settings ───────────────────────────────────────────────────────
PAGE_ICON = "📊"
PAGE_TITLE = "AI Smart Investment System"
REFRESH_INTERVAL_SECONDS = 300         # Auto-refresh every 5 minutes
