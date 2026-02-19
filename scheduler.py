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
        from data.stocktwits_fetcher import fetch_stocktwits_posts
        from analysis.sentiment import compute_sentiment_signal

        articles = fetch_news(symbol)
        posts = fetch_reddit_posts(symbol, asset_type=asset_type)
        social_texts = [p["title"] for p in posts if p.get("title")]

        # Add StockTwits (real-time retail sentiment, no auth required)
        twits = fetch_stocktwits_posts(symbol)
        social_texts.extend(twits)

        if articles or social_texts:
            result = compute_sentiment_signal(articles, social_texts)
            logger.debug(
                "Sentiment for %s: score=%.3f conf=%.3f "
                "(news=%d reddit=%d twits=%d)",
                symbol, result["score"], result["confidence"],
                result.get("news_count", 0),
                len([p for p in posts if p.get("title")]),
                len(twits),
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

    # Run accuracy check on past signals (fills outcome_return_5d / outcome_correct)
    try:
        from analysis.accuracy_tracker import run_accuracy_check
        acc = run_accuracy_check()
        if acc["checked"] > 0:
            logger.info(
                "Accuracy check: %d signals evaluated, %.1f%% correct",
                acc["checked"], acc["accuracy"] * 100,
            )
    except Exception as exc:
        logger.warning("Accuracy check failed: %s", exc)

    # Fetch global signals once per scan (all 4-hour cached inside their modules)
    from analysis.macro_signals import get_macro_signal
    from analysis.market_breadth import get_market_breadth
    from analysis.intermarket import get_intermarket_signal
    from analysis.fear_greed import get_fear_greed_signal
    try:
        macro_signal = get_macro_signal()
        logger.info("Macro signal: score=%.3f regime=%s conf=%.2f",
                    macro_signal["score"], macro_signal["regime"],
                    macro_signal["confidence"])
    except Exception as exc:
        logger.warning("Macro fetch failed, using None: %s", exc)
        macro_signal = None

    try:
        breadth_signal = get_market_breadth()
        logger.info("Market breadth: score=%.3f regime=%s above200=%.0f%%",
                    breadth_signal["score"], breadth_signal["regime"],
                    (breadth_signal.get("pct_above_200ma") or 0) * 100)
    except Exception as exc:
        logger.warning("Breadth fetch failed, using None: %s", exc)
        breadth_signal = None

    try:
        intermarket_signal = get_intermarket_signal()
        logger.info("Intermarket: score=%.3f regime=%s",
                    intermarket_signal["score"], intermarket_signal["regime"])
    except Exception as exc:
        logger.warning("Intermarket fetch failed, using None: %s", exc)
        intermarket_signal = None

    try:
        stock_fg_signal  = get_fear_greed_signal("stock")
        crypto_fg_signal = get_fear_greed_signal("crypto")
        logger.info("Fear & Greed: stock=%s (%.0f) crypto=%s (%.0f)",
                    stock_fg_signal["fg_label"],  stock_fg_signal["fg_index"],
                    crypto_fg_signal["fg_label"], crypto_fg_signal["fg_index"])
    except Exception as exc:
        logger.warning("Fear & Greed fetch failed, using None: %s", exc)
        stock_fg_signal = crypto_fg_signal = None

    def _process_symbol(symbol: str, df, asset_type: str):
        """Compute and persist a signal for one symbol (captures local imports)."""
        from analysis.multi_timeframe import compute_mtf_signal
        from analysis.earnings_filter import get_earnings_filter
        from analysis.analyst_consensus import get_analyst_consensus

        cache_price_data(symbol, df, asset_type)
        tech_signal = compute_technical_signal(df)
        sentiment_signal = _build_sentiment_signal(symbol, asset_type)
        ml_signal = _build_ml_signal(symbol, df)

        # Multi-timeframe confluence (reuses daily df; fetches intraday for stocks)
        try:
            mtf_signal = compute_mtf_signal(symbol, asset_type, df)
            logger.debug("MTF %s: score=%.3f alignment=%.2f TFs=%s",
                         symbol, mtf_signal["score"], mtf_signal["alignment"],
                         mtf_signal["timeframes_available"])
        except Exception as exc:
            logger.warning("MTF signal failed for %s: %s", symbol, exc)
            mtf_signal = None

        # Earnings proximity filter (stocks only; no-op for crypto)
        try:
            earnings_filter = get_earnings_filter(symbol)
        except Exception as exc:
            logger.warning("Earnings filter failed for %s: %s", symbol, exc)
            earnings_filter = None

        # Analyst consensus (stocks only; no-op for crypto)
        try:
            analyst_signal = get_analyst_consensus(symbol)
        except Exception as exc:
            logger.warning("Analyst consensus failed for %s: %s", symbol, exc)
            analyst_signal = None

        # Sector rotation (4-hour cached overview; per-symbol lookup)
        try:
            from analysis.sector_rotation import get_sector_signal
            sector_signal = get_sector_signal(symbol, asset_type)
        except Exception as exc:
            logger.warning("Sector signal failed for %s: %s", symbol, exc)
            sector_signal = None

        # Short interest squeeze detector (24-hour cached; crypto returns neutral)
        try:
            from analysis.short_interest import get_short_interest_signal
            short_interest_signal = get_short_interest_signal(symbol, asset_type, df)
        except Exception as exc:
            logger.warning("Short interest failed for %s: %s", symbol, exc)
            short_interest_signal = None

        # Options sentiment: put/call ratio + IV skew (2-hour cached; crypto N/A)
        try:
            from analysis.options_signal import get_options_signal
            options_signal = get_options_signal(symbol, asset_type)
        except Exception as exc:
            logger.warning("Options signal failed for %s: %s", symbol, exc)
            options_signal = None

        fg_signal = crypto_fg_signal if asset_type == "crypto" else stock_fg_signal
        combined = combine_signals(
            tech_signal, sentiment_signal, ml_signal,
            macro=macro_signal,
            mtf=mtf_signal,
            earnings_filter=earnings_filter,
            breadth=breadth_signal,
            analyst=analyst_signal,
            intermarket=intermarket_signal,
            fear_greed=fg_signal,
            sector=sector_signal,
            short_interest=short_interest_signal,
            options=options_signal,
        )
        combined["symbol"] = symbol
        save_signal(
            symbol=symbol, signal_type="scheduled",
            direction=combined["direction"], strength=combined["strength"],
            confidence=combined["confidence"],
            technical_score=combined["technical_score"],
            sentiment_score=sentiment_signal["score"],
            ml_score=ml_signal["score"],
            macro_score=combined.get("macro_score"),
            macro_regime=combined.get("macro_regime"),
        )
        if combined["direction"] in ("BUY", "SELL"):
            notify_signal(symbol, combined)
        all_signals.append(combined)

        earnings_note = f" earnings:{combined['earnings_warning']}" if combined.get("earnings_warning") else ""
        logger.info(
            "Scheduled signal for %s: %s "
            "(tech=%.2f sent=%.2f ml=%.2f macro=%.2f [%s] "
            "mtf=%.2f breadth=%s analyst=%s sector=%s si=%s)%s",
            symbol, combined["direction"],
            combined["technical_score"],
            sentiment_signal["score"],
            ml_signal["score"],
            combined.get("macro_score", 0.0),
            combined.get("macro_regime", "N/A"),
            combined.get("mtf_alignment", 0.5),
            combined.get("breadth_regime", "N/A"),
            combined.get("analyst_label", "N/A"),
            combined.get("sector_regime", "N/A"),
            combined.get("short_interest_regime", "N/A"),
            earnings_note,
        )

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
