"""Scheduler: automatic data refresh and daily signal generation."""

import threading
import logging
from datetime import datetime

from logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

_scheduler_thread = None
_running = False
_stop_event = threading.Event()

_NEUTRAL_SIGNAL = {"score": 0, "confidence": 0.3}


def _build_sentiment_signal(symbol: str, asset_type: str) -> dict:
    """Fetch news + social data and compute sentiment signal.

    Falls back to a neutral placeholder if APIs are unavailable or fail.
    """
    try:
        from data.news_fetcher import fetch_news
        from data.social_fetcher import fetch_reddit_posts
        from analysis.sentiment import compute_sentiment_signal

        articles = fetch_news(symbol)
        posts = fetch_reddit_posts(symbol, asset_type=asset_type)
        social_texts = [p["title"] for p in posts if p.get("title")]

        if articles or social_texts:
            result = compute_sentiment_signal(articles, social_texts)
            logger.debug(
                "Sentiment for %s: score=%.3f conf=%.3f (news=%d social=%d)",
                symbol, result["score"], result["confidence"],
                result.get("news_count", 0), result.get("social_count", 0),
            )
            return result
    except Exception as e:
        logger.warning("Sentiment signal failed for %s: %s", symbol, e)

    return _NEUTRAL_SIGNAL


def _build_ml_signal(symbol: str, df) -> dict:
    """Compute combined ML signal (XGBoost + LightGBM + LSTM).

    Loads saved models and only retrains when the model is stale.
    Falls back to a neutral placeholder on any error.
    """
    try:
        from analysis.ml_models import compute_ml_signal

        result = compute_ml_signal(df, symbol, train_if_needed=True)
        logger.debug(
            "ML signal for %s: score=%.3f conf=%.3f",
            symbol, result["score"], result["confidence"],
        )
        return result
    except Exception as e:
        logger.warning("ML signal failed for %s: %s", symbol, e)

    return _NEUTRAL_SIGNAL


def _run_signal_scan():
    """Generate signals for all watchlist symbols."""
    from config import DEFAULT_STOCKS, DEFAULT_CRYPTO
    from db.models import get_setting
    from data.stock_fetcher import fetch_stock_data
    from data.crypto_fetcher import fetch_crypto_data
    from data.cache_manager import cache_price_data
    from analysis.technical import compute_technical_signal
    from strategy.signal_combiner import combine_signals
    from db.models import save_signal
    from data.notifier import notify_signal, notify_daily_summary

    stocks = get_setting("watchlist_stocks", DEFAULT_STOCKS)
    cryptos = get_setting("watchlist_crypto", DEFAULT_CRYPTO)

    all_signals = []

    def _process_symbol(symbol: str, df, asset_type: str):
        """Compute and persist a signal for one symbol (captures local imports)."""
        cache_price_data(symbol, df, asset_type)
        tech_signal = compute_technical_signal(df)
        sentiment_signal = _build_sentiment_signal(symbol, asset_type)
        ml_signal = _build_ml_signal(symbol, df)
        combined = combine_signals(tech_signal, sentiment_signal, ml_signal)
        combined["symbol"] = symbol
        save_signal(
            symbol=symbol, signal_type="scheduled",
            direction=combined["direction"], strength=combined["strength"],
            confidence=combined["confidence"],
            technical_score=combined["technical_score"],
            sentiment_score=sentiment_signal["score"],
            ml_score=ml_signal["score"],
        )
        if combined["direction"] in ("BUY", "SELL"):
            notify_signal(symbol, combined)
        all_signals.append(combined)
        logger.info("Scheduled signal for %s: %s (tech=%.2f sent=%.2f ml=%.2f)",
                    symbol, combined["direction"],
                    combined["technical_score"],
                    sentiment_signal["score"],
                    ml_signal["score"])

    # Stocks
    for sym in stocks:
        try:
            df = fetch_stock_data(sym, period="2y")
            if df is None or df.empty:
                continue
            _process_symbol(sym, df, "stock")
        except Exception as e:
            logger.warning("Scheduled scan failed for %s: %s", sym, e)

    # Crypto
    for pair in cryptos:
        try:
            df = fetch_crypto_data(pair, days=730)
            if df is None or df.empty:
                continue
            _process_symbol(pair, df, "crypto")
        except Exception as e:
            logger.warning("Scheduled scan failed for %s: %s", pair, e)

    # Daily summary
    notify_daily_summary(all_signals)
    logger.info("Scheduled scan complete: %d signals generated", len(all_signals))
    return all_signals


def _scheduler_loop(interval_minutes: int):
    """Background loop that runs scans at the configured interval."""
    global _running
    while _running:
        try:
            now = datetime.now()
            logger.info("Scheduler: starting scan at %s", now.strftime("%H:%M"))
            _run_signal_scan()
        except Exception as e:
            logger.error("Scheduler error: %s", e)

        # Block until the interval elapses or stop_scheduler() sets the event
        _stop_event.wait(timeout=interval_minutes * 60)
        _stop_event.clear()


def start_scheduler(interval_minutes: int = 60):
    """Start the background scheduler thread."""
    global _scheduler_thread, _running
    if _running:
        logger.info("Scheduler already running")
        return

    _running = True
    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(interval_minutes,),
        daemon=True,
        name="ai_invest_scheduler",
    )
    _scheduler_thread.start()
    logger.info("Scheduler started (interval: %d min)", interval_minutes)


def stop_scheduler():
    """Stop the background scheduler."""
    global _running
    _running = False
    _stop_event.set()  # Wake the sleeping loop immediately
    logger.info("Scheduler stopped")


def is_running() -> bool:
    return _running


def run_scan_now() -> list[dict]:
    """Run a signal scan immediately (blocking)."""
    return _run_signal_scan()
