"""AI Trading Signals - Multi-factor signal cards, breakdown, history."""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data.stock_fetcher import fetch_stock_data
from data.crypto_fetcher import fetch_crypto_data
from data.news_fetcher import fetch_news
from data.social_fetcher import fetch_reddit_posts
from data.cache_manager import cache_price_data, get_cached_price_data
from analysis.technical import compute_technical_signal, compute_all_indicators
from analysis.sentiment import compute_sentiment_signal
from analysis.ml_models import compute_ml_signal
from strategy.signal_combiner import combine_signals
from dashboard.components.metrics_cards import signal_card
from dashboard.components.signal_display import factor_breakdown, signal_table
from dashboard.components.charts import candlestick_chart, line_chart
from db.models import save_signal, get_latest_signals, get_signal_history
from config import DEFAULT_STOCKS, DEFAULT_CRYPTO

st.title("🤖 AI Trading Signals")

st.warning("⚠️ Disclaimer: Signals are for educational/reference purposes only. Not investment advice.")

# ── Symbol Selection ──────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])
with col1:
    asset_type = st.radio("Asset Type", ["Stock", "Crypto"], horizontal=True, key="sig_type")
with col2:
    if asset_type == "Stock":
        symbol = st.selectbox("Select Symbol", DEFAULT_STOCKS, key="sig_symbol")
    else:
        symbol = st.selectbox("Select Symbol", DEFAULT_CRYPTO, key="sig_crypto")

generate = st.button("🔄 Generate Signal", type="primary", use_container_width=True)

# ── Signal Generation ─────────────────────────────────────────────────
if generate:
    with st.spinner(f"Analyzing {symbol}..."):
        # 1. Fetch price data
        try:
            if asset_type == "Stock":
                df = get_cached_price_data(symbol, "stock")
                if df is None:
                    df = fetch_stock_data(symbol, period="2y")
                    if not df.empty:
                        cache_price_data(symbol, df, "stock")
            else:
                df = get_cached_price_data(symbol, "crypto")
                if df is None:
                    df = fetch_crypto_data(symbol, days=730)
                    if not df.empty:
                        cache_price_data(symbol, df, "crypto")

            if df is None or df.empty:
                st.error(f"Could not fetch data for {symbol}")
                st.stop()
        except Exception as e:
            st.error(f"Data fetch error: {e}")
            st.stop()

        # 2. Technical analysis
        st.info("Computing technical indicators...")
        tech_signal = compute_technical_signal(df)

        # 3. Sentiment analysis
        st.info("Analyzing market sentiment...")
        try:
            news = fetch_news(symbol.split("/")[0])
            social = [p["title"] + " " + p.get("text", "")
                      for p in fetch_reddit_posts(symbol.split("/")[0],
                                                  "crypto" if asset_type == "Crypto" else "stock")]
            sent_signal = compute_sentiment_signal(news, social)
        except Exception:
            sent_signal = {"score": 0, "confidence": 0.3, "news_sentiment": 0,
                           "social_sentiment": 0, "news_count": 0, "social_count": 0}

        # 4. ML prediction
        st.info("Running ML models...")
        try:
            ml_signal = compute_ml_signal(df, symbol, train_if_needed=True)
        except Exception:
            ml_signal = {"score": 0, "confidence": 0.3}

        # 5. Combine signals
        combined = combine_signals(tech_signal, sent_signal, ml_signal)

        # Save to DB
        save_signal(
            symbol=symbol,
            signal_type="combined",
            direction=combined["direction"],
            strength=combined["strength"],
            confidence=combined["confidence"],
            technical_score=combined["technical_score"],
            sentiment_score=combined["sentiment_score"],
            ml_score=combined["ml_score"],
        )

    # ── Display Results ───────────────────────────────────────────────
    st.divider()
    signal_card(symbol, combined["direction"], combined["confidence"],
                combined["strength"], combined["technical_score"],
                combined["sentiment_score"], combined["ml_score"])

    st.divider()
    st.subheader("Factor Breakdown")
    factor_breakdown(combined["technical_score"], combined["sentiment_score"],
                     combined["ml_score"])

    # Technical details
    with st.expander("📊 Technical Analysis Details"):
        st.json(tech_signal)

    with st.expander("📰 Sentiment Analysis Details"):
        st.write(f"News articles analyzed: {sent_signal.get('news_count', 0)}")
        st.write(f"Social posts analyzed: {sent_signal.get('social_count', 0)}")
        st.write(f"News sentiment: {sent_signal.get('news_sentiment', 0):+.4f}")
        st.write(f"Social sentiment: {sent_signal.get('social_sentiment', 0):+.4f}")

    with st.expander("🤖 ML Model Details"):
        st.json(ml_signal)

    # Chart with indicators
    st.divider()
    st.subheader("Price Chart with Indicators")
    indicators_df = compute_all_indicators(df)
    overlay = {
        "SMA_20": indicators_df.get("SMA_20"),
        "SMA_50": indicators_df.get("SMA_50"),
        "BB_upper": indicators_df.get("BB_upper"),
        "BB_lower": indicators_df.get("BB_lower"),
    }
    fig = candlestick_chart(df.tail(120), symbol, indicators={k: v.tail(120) if v is not None else None for k, v in overlay.items()})
    st.plotly_chart(fig, use_container_width=True)

# ── Signal History ────────────────────────────────────────────────────
st.divider()
st.subheader("Recent Signals")
recent = get_latest_signals(30)
if recent:
    signal_table(recent)
else:
    st.caption("No signals generated yet. Click 'Generate Signal' above.")
