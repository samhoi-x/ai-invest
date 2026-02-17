"""System Settings - API keys, weights, risk params, watchlist, data management."""

import streamlit as st
import pandas as pd
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from i18n import t

from db.models import get_setting, set_setting
from data.cache_manager import clear_cache
from config import SIGNAL_WEIGHTS, RISK, DEFAULT_STOCKS, DEFAULT_CRYPTO

st.title(f"\u2699\ufe0f {t('settings')}")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    t("api_keys"), t("notifications"), t("signal_weights"), t("risk_parameters"), t("watchlist"), t("data_management")
])

# ── API Keys ──────────────────────────────────────────────────────────
with tab1:
    st.subheader("API Key Management")
    st.caption("Keys are stored locally in the database. Never shared externally.")

    with st.form("api_keys"):
        marketaux = st.text_input("MarketAux API Key",
                                  value=get_setting("marketaux_key", ""),
                                  type="password")
        finnhub = st.text_input("Finnhub API Key",
                                value=get_setting("finnhub_key", ""),
                                type="password")
        reddit_id = st.text_input("Reddit Client ID",
                                  value=get_setting("reddit_client_id", ""))
        reddit_secret = st.text_input("Reddit Client Secret",
                                      value=get_setting("reddit_client_secret", ""),
                                      type="password")

        if st.form_submit_button("Save API Keys", type="primary"):
            set_setting("marketaux_key", marketaux)
            set_setting("finnhub_key", finnhub)
            set_setting("reddit_client_id", reddit_id)
            set_setting("reddit_client_secret", reddit_secret)
            st.success("API keys saved.")

    st.markdown("""
    **Getting free API keys:**
    - **MarketAux:** [marketaux.com](https://www.marketaux.com/) (100 req/day free)
    - **Finnhub:** [finnhub.io](https://finnhub.io/) (60 calls/min free)
    - **Reddit:** [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (Create script app)
    """)

# ── Notifications ────────────────────────────────────────────────────
with tab2:
    st.subheader("Telegram Notifications")
    st.caption("Receive BUY/SELL signals and risk alerts via Telegram.")

    with st.form("telegram_config"):
        tg_token = st.text_input("Bot Token (from @BotFather)",
                                  value=get_setting("telegram_bot_token", ""),
                                  type="password")
        tg_chat = st.text_input("Chat ID",
                                 value=get_setting("telegram_chat_id", ""))
        tg_enabled = st.checkbox("Enable notifications",
                                  value=bool(get_setting("telegram_enabled", False)))

        if st.form_submit_button("Save Telegram Settings", type="primary"):
            set_setting("telegram_bot_token", tg_token)
            set_setting("telegram_chat_id", tg_chat)
            set_setting("telegram_enabled", tg_enabled)
            st.success("Telegram settings saved.")

    if st.button("Send Test Message"):
        from data.notifier import send_telegram
        token = get_setting("telegram_bot_token", "")
        chat = get_setting("telegram_chat_id", "")
        if token and chat:
            ok = send_telegram(token, chat, "\u2705 <b>AI Smart Invest</b>\nTest message — notifications working!")
            if ok:
                st.success("Test message sent! Check your Telegram.")
            else:
                st.error("Failed to send. Check token and chat ID.")
        else:
            st.warning("Please configure bot token and chat ID first.")

    st.markdown("""
    **Setup steps:**
    1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy the token
    2. Message your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID
    3. For group notifications: add bot to group, send a message, check getUpdates for the group chat ID
    """)

# ── Signal Weights ────────────────────────────────────────────────────
with tab3:
    st.subheader("Signal Weight Adjustment")
    st.caption("Adjust how much each factor contributes to the final signal.")

    saved_weights = get_setting("signal_weights", SIGNAL_WEIGHTS)

    with st.form("signal_weights"):
        tech_w = st.slider("Technical Analysis Weight", 0.0, 1.0,
                           float(saved_weights.get("technical", 0.35)), 0.05)
        sent_w = st.slider("Sentiment Analysis Weight", 0.0, 1.0,
                           float(saved_weights.get("sentiment", 0.25)), 0.05)
        ml_w = st.slider("ML Prediction Weight", 0.0, 1.0,
                         float(saved_weights.get("ml", 0.40)), 0.05)

        total = tech_w + sent_w + ml_w
        if abs(total - 1.0) > 0.01:
            st.warning(f"Weights sum to {total:.2f}. Should be 1.0.")
        else:
            st.success(f"Weights balanced: {total:.2f}")

        st.divider()
        st.subheader("Signal Thresholds")
        buy_thresh = st.slider("BUY Threshold", 0.0, 1.0,
                               float(get_setting("buy_threshold", 0.3)), 0.05)
        sell_thresh = st.slider("SELL Threshold", -1.0, 0.0,
                                float(get_setting("sell_threshold", -0.2)), 0.05)
        buy_conf = st.slider("BUY Min Confidence", 0.0, 1.0,
                             float(get_setting("buy_confidence_min", 0.65)), 0.05)
        sell_conf = st.slider("SELL Min Confidence", 0.0, 1.0,
                              float(get_setting("sell_confidence_min", 0.50)), 0.05)

        if st.form_submit_button("Save Weights", type="primary"):
            set_setting("signal_weights", {
                "technical": tech_w, "sentiment": sent_w, "ml": ml_w
            })
            set_setting("buy_threshold", buy_thresh)
            set_setting("sell_threshold", sell_thresh)
            set_setting("buy_confidence_min", buy_conf)
            set_setting("sell_confidence_min", sell_conf)
            st.success("Signal weights and thresholds saved.")

# ── Risk Parameters ───────────────────────────────────────────────────
with tab4:
    st.subheader("Risk Parameters")
    st.caption("Configure risk management rules for your portfolio.")

    saved_risk = get_setting("risk_params", RISK)

    with st.form("risk_params"):
        max_pos = st.number_input("Max Single Position (%)",
                                  value=int(saved_risk.get("max_single_position", 0.15) * 100),
                                  min_value=1, max_value=50)
        max_crypto = st.number_input("Max Crypto Allocation (%)",
                                     value=int(saved_risk.get("max_crypto_allocation", 0.30) * 100),
                                     min_value=0, max_value=100)
        max_sector = st.number_input("Max Sector Concentration (%)",
                                     value=int(saved_risk.get("max_sector_concentration", 0.35) * 100),
                                     min_value=1, max_value=100)
        min_cash = st.number_input("Min Cash Reserve (%)",
                                   value=int(saved_risk.get("min_cash_reserve", 0.10) * 100),
                                   min_value=0, max_value=50)

        st.divider()
        st.subheader("Drawdown Protection")
        dd_warn = st.number_input("Drawdown Warning (%)",
                                  value=int(saved_risk.get("drawdown_warning", 0.08) * 100),
                                  min_value=1, max_value=50)
        dd_halt = st.number_input("Drawdown Halt (%)",
                                  value=int(saved_risk.get("drawdown_halt", 0.12) * 100),
                                  min_value=1, max_value=50)
        dd_reduce = st.number_input("Drawdown Reduce (%)",
                                    value=int(saved_risk.get("drawdown_reduce", 0.15) * 100),
                                    min_value=1, max_value=50)

        if st.form_submit_button("Save Risk Parameters", type="primary"):
            set_setting("risk_params", {
                "max_single_position": max_pos / 100,
                "max_crypto_allocation": max_crypto / 100,
                "max_sector_concentration": max_sector / 100,
                "max_trade_risk": 0.01,
                "min_cash_reserve": min_cash / 100,
                "drawdown_warning": dd_warn / 100,
                "drawdown_halt": dd_halt / 100,
                "drawdown_reduce": dd_reduce / 100,
            })
            st.success("Risk parameters saved.")

# ── Watchlist ─────────────────────────────────────────────────────────
with tab5:
    st.subheader("Watchlist Management")

    saved_stocks = get_setting("watchlist_stocks", DEFAULT_STOCKS)
    saved_crypto = get_setting("watchlist_crypto", DEFAULT_CRYPTO)

    with st.form("watchlist"):
        stock_text = st.text_area("Stock Symbols (one per line)",
                                  "\n".join(saved_stocks if isinstance(saved_stocks, list) else DEFAULT_STOCKS))
        crypto_text = st.text_area("Crypto Pairs (one per line)",
                                   "\n".join(saved_crypto if isinstance(saved_crypto, list) else DEFAULT_CRYPTO))

        if st.form_submit_button("Save Watchlist", type="primary"):
            stocks = [s.strip().upper() for s in stock_text.strip().split("\n") if s.strip()]
            cryptos = [s.strip() for s in crypto_text.strip().split("\n") if s.strip()]
            set_setting("watchlist_stocks", stocks)
            set_setting("watchlist_crypto", cryptos)
            st.success(f"Saved {len(stocks)} stocks and {len(cryptos)} crypto pairs.")

# ── Scheduler ────────────────────────────────────────────────────────
with tab6:
    st.subheader("Auto Scheduler")
    st.caption("Automatically scan watchlist and generate signals on a schedule.")

    from scheduler import start_scheduler, stop_scheduler, is_running, run_scan_now

    status_icon = "\U0001f7e2" if is_running() else "\U0001f534"
    st.write(f"Scheduler status: {status_icon} {'Running' if is_running() else 'Stopped'}")

    sched_interval = st.number_input("Scan interval (minutes)", value=60, min_value=5, max_value=1440, step=5)

    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        if st.button("Start Scheduler", type="primary", use_container_width=True, disabled=is_running()):
            start_scheduler(sched_interval)
            st.success(f"Scheduler started (every {sched_interval} min)")
            st.rerun()
    with scol2:
        if st.button("Stop Scheduler", use_container_width=True, disabled=not is_running()):
            stop_scheduler()
            st.success("Scheduler stopped")
            st.rerun()
    with scol3:
        if st.button("Run Scan Now", use_container_width=True):
            with st.spinner("Scanning all watchlist symbols..."):
                signals = run_scan_now()
            st.success(f"Scan complete: {len(signals)} signals generated")

    st.divider()
    st.subheader("Data Management")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Clear Price Cache", use_container_width=True):
            clear_cache("price")
            st.success("Price cache cleared.")

    with col2:
        if st.button("Clear News Cache", use_container_width=True):
            clear_cache("news")
            st.success("News cache cleared.")

    with col3:
        if st.button("Clear All Caches", type="secondary", use_container_width=True):
            clear_cache("all")
            st.success("All caches cleared.")

    st.divider()
    st.subheader("Export Data")

    export_type = st.selectbox("Export Type", ["Signals", "Transactions", "Backtest Results"])
    if st.button("Export as CSV"):
        from db.models import get_latest_signals, get_transactions, get_backtest_results
        if export_type == "Signals":
            data = get_latest_signals(1000)
        elif export_type == "Transactions":
            data = get_transactions(1000)
        else:
            data = get_backtest_results(100)

        if data:
            df = pd.DataFrame(data)
            csv = df.to_csv(index=False)
            st.download_button(
                f"Download {export_type} CSV",
                csv,
                f"{export_type.lower().replace(' ', '_')}.csv",
                "text/csv",
            )
        else:
            st.caption("No data to export.")

    st.divider()
    st.subheader("System Info")
    import config
    st.json({
        "Database": str(config.DB_PATH),
        "Models Directory": str(config.MODELS_DIR),
        "Cache TTL (price)": f"{config.CACHE_TTL['price_minutes']} min",
        "Cache TTL (news)": f"{config.CACHE_TTL['news_minutes']} min",
        "Cache TTL (sentiment)": f"{config.CACHE_TTL['sentiment_minutes']} min",
    })
