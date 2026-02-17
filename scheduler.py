"""Scheduler: automatic data refresh and daily signal generation."""

import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler_thread = None
_running = False


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

    # Stocks
    for sym in stocks:
        try:
            df = fetch_stock_data(sym, period="2y")
            if df is None or df.empty:
                continue
            cache_price_data(sym, df, "stock")

            tech_signal = compute_technical_signal(df)
            # Use tech-only for scheduled scans (sentiment/ML too slow for batch)
            combined = combine_signals(
                tech_signal,
                {"score": 0, "confidence": 0.3},
                {"score": 0, "confidence": 0.3},
            )
            combined["symbol"] = sym

            save_signal(
                symbol=sym, signal_type="scheduled",
                direction=combined["direction"], strength=combined["strength"],
                confidence=combined["confidence"],
                technical_score=combined["technical_score"],
                sentiment_score=0, ml_score=0,
            )

            if combined["direction"] in ("BUY", "SELL"):
                notify_signal(sym, combined)

            all_signals.append(combined)
            logger.info("Scheduled signal for %s: %s", sym, combined["direction"])
        except Exception as e:
            logger.warning("Scheduled scan failed for %s: %s", sym, e)

    # Crypto
    for pair in cryptos:
        try:
            df = fetch_crypto_data(pair, days=730)
            if df is None or df.empty:
                continue
            cache_price_data(pair, df, "crypto")

            tech_signal = compute_technical_signal(df)
            combined = combine_signals(
                tech_signal,
                {"score": 0, "confidence": 0.3},
                {"score": 0, "confidence": 0.3},
            )
            combined["symbol"] = pair

            save_signal(
                symbol=pair, signal_type="scheduled",
                direction=combined["direction"], strength=combined["strength"],
                confidence=combined["confidence"],
                technical_score=combined["technical_score"],
                sentiment_score=0, ml_score=0,
            )

            if combined["direction"] in ("BUY", "SELL"):
                notify_signal(pair, combined)

            all_signals.append(combined)
            logger.info("Scheduled signal for %s: %s", pair, combined["direction"])
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

        # Sleep in small increments so we can stop quickly
        for _ in range(interval_minutes * 60):
            if not _running:
                break
            time.sleep(1)


def start_scheduler(interval_minutes: int = 60):
    """Start the background scheduler thread."""
    global _scheduler_thread, _running
    if _running:
        logger.info("Scheduler already running")
        return

    _running = True
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
    logger.info("Scheduler stopped")


def is_running() -> bool:
    return _running


def run_scan_now() -> list[dict]:
    """Run a signal scan immediately (blocking)."""
    return _run_signal_scan()
