"""Market Overview - Real-time quotes, charts, heatmap, watchlist, news."""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data.stock_fetcher import fetch_stock_data, get_current_price
from data.crypto_fetcher import get_crypto_price, fetch_crypto_data
from data.cache_manager import cache_price_data, get_cached_price_data
from data.ws_price_feed import get_live_price, start_price_feed, is_feed_running
from dashboard.components.charts import candlestick_chart, heatmap_chart
from dashboard.components.metrics_cards import price_card
from config import DEFAULT_STOCKS, DEFAULT_CRYPTO
from i18n import t

# Auto-start WebSocket price feed if not running
if not is_feed_running():
    start_price_feed(DEFAULT_CRYPTO)

st.title(f"\U0001f310 {t('market_overview')}")

# ── Top Index / Crypto Prices ─────────────────────────────────────────
st.subheader(t("market_snapshot"))
index_symbols = ["SPY", "QQQ", "DIA"]
crypto_symbols = ["BTC/USDT", "ETH/USDT"]

col_count = len(index_symbols) + len(crypto_symbols)
cols = st.columns(col_count)

with st.spinner(t("fetching")):
    for i, sym in enumerate(index_symbols):
        with cols[i]:
            data = get_current_price(sym)
            if data:
                price_card(sym, data["price"], data["change"], data["change_pct"])
            else:
                st.metric(sym, "—", "—")

    for i, sym in enumerate(crypto_symbols):
        with cols[len(index_symbols) + i]:
            # Prefer WebSocket live data, fallback to REST
            data = get_live_price(sym) or get_crypto_price(sym)
            if data:
                price_card(sym.split("/")[0], data["price"], data["change"], data["change_pct"])
            else:
                st.metric(sym.split("/")[0], "—", "—")

st.divider()

# ── Interactive Chart ─────────────────────────────────────────────────
st.subheader(t("price_chart"))

chart_col1, chart_col2 = st.columns([3, 1])
with chart_col2:
    asset_type = st.radio(t("asset_type"), [t("stock"), t("crypto")], horizontal=True)
    if asset_type == t("stock"):
        symbol = st.selectbox(t("select_symbol"), DEFAULT_STOCKS)
        period = st.selectbox(t("period"), ["1mo", "3mo", "6mo", "1y", "2y"], index=3)
    else:
        symbol = st.selectbox(t("select_symbol"), DEFAULT_CRYPTO)
        period_days = st.selectbox(t("period"), [30, 90, 180, 365, 730],
                                   format_func=lambda x: f"{x} days", index=3)

with chart_col1:
    with st.spinner(f"{t('loading')} {symbol}..."):
        try:
            if asset_type == t("stock"):
                # Try cache first
                df = get_cached_price_data(symbol, "stock")
                if df is None:
                    df = fetch_stock_data(symbol, period=period)
                    if not df.empty:
                        cache_price_data(symbol, df, "stock")
            else:
                df = get_cached_price_data(symbol, "crypto")
                if df is None:
                    df = fetch_crypto_data(symbol, days=period_days)
                    if not df.empty:
                        cache_price_data(symbol, df, "crypto")

            if df is not None and not df.empty:
                fig = candlestick_chart(df, symbol)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"{t('no_data')}: {symbol}")
        except Exception as e:
            st.error(f"Error loading data: {e}")

st.divider()

# ── Watchlist ─────────────────────────────────────────────────────────
st.subheader(t("watchlist"))

tab_stock, tab_crypto = st.tabs([t("stock"), t("crypto")])

with tab_stock:
    with st.spinner("Loading stock prices..."):
        stock_data = []
        for sym in DEFAULT_STOCKS:
            data = get_current_price(sym)
            if data:
                stock_data.append(data)
        if stock_data:
            df_stocks = pd.DataFrame(stock_data)
            st.dataframe(
                df_stocks.style.map(
                    lambda v: "color: #26a69a" if v > 0 else "color: #ef5350" if v < 0 else "",
                    subset=["change", "change_pct"]
                ),
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("Unable to fetch stock prices.")

with tab_crypto:
    with st.spinner("Loading crypto prices..."):
        crypto_data = []
        for pair in DEFAULT_CRYPTO:
            data = get_crypto_price(pair)
            if data:
                crypto_data.append(data)
        if crypto_data:
            df_crypto = pd.DataFrame(crypto_data)
            st.dataframe(
                df_crypto.style.map(
                    lambda v: "color: #26a69a" if v > 0 else "color: #ef5350" if v < 0 else "",
                    subset=["change", "change_pct"]
                ),
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("Unable to fetch crypto prices.")

# ── Market Heatmap ────────────────────────────────────────────────────
st.divider()
st.subheader(t("correlation_heatmap"))

with st.spinner(f"{t('computing')}..."):
    try:
        close_data = {}
        for sym in DEFAULT_STOCKS[:6]:
            cached = get_cached_price_data(sym, "stock")
            if cached is not None and not cached.empty:
                close_data[sym] = cached["close"]
            else:
                df_tmp = fetch_stock_data(sym, period="6mo")
                if not df_tmp.empty:
                    close_data[sym] = df_tmp["close"]
                    cache_price_data(sym, df_tmp, "stock")

        if len(close_data) >= 2:
            corr_df = pd.DataFrame(close_data).pct_change().dropna().corr()
            fig = heatmap_chart(corr_df, "Return Correlation (6M)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Need at least 2 stocks for correlation heatmap.")
    except Exception as e:
        st.caption(f"Could not compute correlations: {e}")
