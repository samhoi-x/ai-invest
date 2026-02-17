# AI Smart Investment System

An AI-powered investment analysis platform built with Streamlit. Combines technical analysis, NLP sentiment analysis, and machine learning to generate trading signals for stocks and cryptocurrencies.

## Features

- **Multi-Factor Signal Generation** — Fuses technical indicators (RSI, MACD, Bollinger Bands, etc.), FinBERT sentiment analysis, and ML models (XGBoost, LightGBM, LSTM) into a single confidence-weighted score
- **7-Page Dashboard** — Market overview, AI signals, portfolio management, risk monitoring, backtesting, performance tracking, and settings
- **Risk Management** — Position limits, drawdown protection (warning/halt/reduce), ATR-based and trailing stop-losses
- **Backtesting Engine** — Event-driven backtester with commission modeling, equity curves, and buy & hold benchmark
- **Portfolio Optimization** — Markowitz mean-variance optimization with rebalancing suggestions
- **Real-Time Data** — Stock prices via yfinance, crypto via CCXT (100+ exchanges), news from MarketAux & Finnhub, Reddit sentiment via PRAW
- **Automated Scheduling** — Background signal scans with Telegram notifications
- **Bilingual UI** — English and Traditional Chinese (繁體中文)

## Project Structure

```
ai_invest/
├── app.py                     # Streamlit entry point
├── config.py                  # Global configuration
├── logger.py                  # Centralized logging
├── scheduler.py               # Automated signal scans
├── i18n.py                    # Internationalization
├── analysis/
│   ├── technical.py           # Technical indicators
│   ├── sentiment.py           # FinBERT sentiment analysis
│   ├── ml_models.py           # XGBoost, LightGBM, LSTM
│   ├── feature_engine.py      # ML feature preparation
│   └── accuracy_tracker.py    # Signal accuracy tracking
├── data/
│   ├── stock_fetcher.py       # Yahoo Finance data
│   ├── crypto_fetcher.py      # CCXT crypto data
│   ├── news_fetcher.py        # MarketAux & Finnhub news
│   ├── social_fetcher.py      # Reddit sentiment
│   ├── cache_manager.py       # TTL-based caching
│   ├── ws_price_feed.py       # WebSocket price feed
│   └── notifier.py            # Telegram notifications
├── db/
│   ├── database.py            # SQLite connection & schema
│   └── models.py              # CRUD operations
├── strategy/
│   ├── signal_combiner.py     # Multi-factor signal fusion
│   ├── backtester.py          # Event-driven backtesting
│   ├── portfolio_optimizer.py # Markowitz optimization
│   └── risk_manager.py        # Position & drawdown limits
├── dashboard/
│   ├── components/            # Reusable UI components
│   └── pages/                 # 7 dashboard pages
└── tests/                     # Unit tests
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys (optional)

```bash
cp .env.example .env
```

Edit `.env` with your keys:

| Service | Free Tier | Purpose |
|---------|-----------|---------|
| [MarketAux](https://www.marketaux.com/) | 100 req/day | Financial news |
| [Finnhub](https://finnhub.io/) | 60 calls/min | Market news |
| [Reddit](https://www.reddit.com/prefs/apps) | Free | Social sentiment |
| [Telegram](https://t.me/BotFather) | Free | Signal notifications |

> The app works without API keys — technical analysis and ML signals only require price data from yfinance/CCXT.

### 3. Run the app

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Market Overview** | Live prices, candlestick charts, correlation heatmap |
| **AI Signals** | Generate and view multi-factor trading signals |
| **Portfolio** | Manage holdings, view allocation, optimize positions |
| **Risk Monitor** | Drawdown tracking, position risk, alert log |
| **Backtest** | Run strategy backtests with performance metrics |
| **Performance** | Signal accuracy stats and factor contribution |
| **Settings** | API keys, notification config, signal weights |

## Configuration

Key defaults in `config.py`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| Buy threshold | 0.3 | Minimum composite score to trigger BUY |
| Buy confidence | 65% | Minimum confidence for BUY |
| Sell threshold | -0.2 | Score below which to trigger SELL |
| Max position | 15% | Max portfolio allocation per asset |
| Max crypto | 30% | Max total crypto allocation |
| Drawdown halt | 12% | Stop new buys at this drawdown |
| Retrain interval | 60 days | ML model retraining frequency |

## Signal Weights

| Factor | Weight |
|--------|--------|
| Technical Analysis | 35% |
| Sentiment (FinBERT) | 25% |
| ML Models (XGBoost + LightGBM + LSTM) | 40% |

## Testing

```bash
pytest tests/
```

76 tests covering technical indicators, sentiment analysis, ML models, signal combination, backtesting, portfolio optimization, risk management, and caching.

## Tech Stack

- **UI**: Streamlit, Plotly
- **Data**: yfinance, CCXT, PRAW, requests
- **ML**: XGBoost, LightGBM, PyTorch (LSTM), scikit-learn
- **NLP**: Hugging Face Transformers (FinBERT)
- **Optimization**: PyPortfolioOpt, CVXPY
- **Database**: SQLite (WAL mode)
- **Notifications**: python-telegram-bot

## License

This project is for educational and research purposes.
