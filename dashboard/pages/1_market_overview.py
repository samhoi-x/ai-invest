"""Market Overview - Real-time quotes, charts, heatmap, watchlist, news."""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data.stock_fetcher import fetch_stock_data, get_current_price
from data.crypto_fetcher import get_crypto_price, fetch_crypto_data
from data.cache_manager import cache_price_data, get_cached_price_data
from data.ws_price_feed import get_live_price, start_price_feed, is_feed_running
from dashboard.components.charts import candlestick_chart, heatmap_chart
from dashboard.components.metrics_cards import price_card
from analysis.macro_signals import get_macro_signal
from analysis.market_breadth import get_market_breadth
from analysis.intermarket import get_intermarket_signal
from analysis.fear_greed import get_fear_greed_signal
from analysis.sector_rotation import get_sector_rotation_overview
from config import DEFAULT_STOCKS, DEFAULT_CRYPTO
from i18n import t

# Auto-start WebSocket price feed if not running
if not is_feed_running():
    start_price_feed(DEFAULT_CRYPTO)

st.title(f"\U0001f310 {t('market_overview')}")

# ── Macro Market Environment ───────────────────────────────────────────
try:
    macro = get_macro_signal()

    # Regime colour mapping
    _regime_colors = {
        "RISK_OFF":    ("#ffcccc", "#c0392b", "🔴"),
        "CAUTIOUS":    ("#fff3cd", "#e67e22", "🟠"),
        "NEUTRAL":     ("#e8f4f8", "#2980b9", "🔵"),
        "CONSTRUCTIVE":("#d4edda", "#27ae60", "🟢"),
        "RISK_ON":     ("#c8f7c5", "#1e8449", "✅"),
        "UNKNOWN":     ("#f0f0f0", "#7f8c8d", "⚪"),
    }
    bg, fg, icon = _regime_colors.get(macro["regime"], _regime_colors["UNKNOWN"])

    st.markdown(
        f"""<div style="background:{bg};border-left:5px solid {fg};
        padding:12px 18px;border-radius:6px;margin-bottom:8px;">
        <b style="color:{fg};font-size:1.1em;">{icon} Macro Market Environment: {macro['regime']}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;Score: <b>{macro['score']:+.3f}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;Confidence: <b>{macro['confidence']*100:.0f}%</b>
        </div>""",
        unsafe_allow_html=True,
    )

    mac_c1, mac_c2, mac_c3 = st.columns(3)

    # VIX card
    with mac_c1:
        vix_lvl = macro.get("vix_level")
        vix_roc = macro.get("vix_change_20d")
        vix_color = "#c0392b" if (vix_lvl or 0) > 20 else "#27ae60"
        st.markdown(
            f"""<div style="border:1px solid {vix_color};border-radius:6px;padding:10px;text-align:center;">
            <div style="color:#888;font-size:.85em;">VIX (Fear Index)</div>
            <div style="font-size:1.6em;font-weight:bold;color:{vix_color};">
            {f"{vix_lvl:.1f}" if vix_lvl else "—"}</div>
            <div style="font-size:.85em;color:#888;">
            20d change: {f"{vix_roc:+.1f}%" if vix_roc is not None else "—"}</div>
            <div style="font-size:.85em;">Score: <b>{macro['vix_score']:+.3f}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )

    # Yield curve card
    with mac_c2:
        spread = macro.get("yield_spread")
        yld_color = "#c0392b" if (spread or 0) < 0 else "#27ae60"
        st.markdown(
            f"""<div style="border:1px solid {yld_color};border-radius:6px;padding:10px;text-align:center;">
            <div style="color:#888;font-size:.85em;">Yield Curve (10Y − 3M)</div>
            <div style="font-size:1.6em;font-weight:bold;color:{yld_color};">
            {f"{spread:+.2f}%" if spread is not None else "—"}</div>
            <div style="font-size:.85em;color:#888;">
            {"Inverted ⚠️" if (spread or 0) < 0 else "Normal ✓"}</div>
            <div style="font-size:.85em;">Score: <b>{macro['yield_score']:+.3f}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )

    # DXY card
    with mac_c3:
        dxy_chg = macro.get("dxy_change_20d")
        dxy_color = "#c0392b" if (dxy_chg or 0) > 2 else "#27ae60"
        st.markdown(
            f"""<div style="border:1px solid {dxy_color};border-radius:6px;padding:10px;text-align:center;">
            <div style="color:#888;font-size:.85em;">DXY (USD Strength)</div>
            <div style="font-size:1.6em;font-weight:bold;color:{dxy_color};">
            {f"{dxy_chg:+.1f}%" if dxy_chg is not None else "—"}</div>
            <div style="font-size:.85em;color:#888;">20-day change</div>
            <div style="font-size:.85em;">Score: <b>{macro['dxy_score']:+.3f}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.caption(
        f"Sources: {', '.join(macro['fetched_sources']) or 'none'} · "
        f"Refreshes every 4 hours"
    )

except Exception as _macro_err:
    st.warning(f"Macro market data unavailable: {_macro_err}")

st.divider()

# ── Market Breadth ─────────────────────────────────────────────────────
try:
    breadth = get_market_breadth()

    _breadth_colors = {
        "HEALTHY": ("#c8f7c5", "#1e8449", "✅"),
        "NEUTRAL": ("#e8f4f8", "#2980b9", "🔵"),
        "WEAK":    ("#fff3cd", "#e67e22", "🟠"),
        "POOR":    ("#ffcccc", "#c0392b", "🔴"),
    }
    bbg, bfg, bicon = _breadth_colors.get(breadth["regime"], _breadth_colors["NEUTRAL"])

    st.markdown(
        f"""<div style="background:{bbg};border-left:5px solid {bfg};
        padding:12px 18px;border-radius:6px;margin-bottom:8px;">
        <b style="color:{bfg};font-size:1.1em;">{bicon} Market Breadth: {breadth['regime']}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;Score: <b>{breadth['score']:+.3f}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;Basket: <b>{breadth['fetched_count']}/{breadth['basket_total']} stocks</b>
        </div>""",
        unsafe_allow_html=True,
    )

    bc1, bc2, bc3 = st.columns(3)
    pct200 = breadth.get("pct_above_200ma")
    ad_r   = breadth.get("ad_ratio")
    adv    = breadth.get("advance_count")
    dec    = breadth.get("decline_count")

    with bc1:
        _c200 = "#27ae60" if (pct200 or 0) >= 0.6 else "#c0392b"
        st.markdown(
            f"""<div style="border:1px solid {_c200};border-radius:6px;
            padding:10px;text-align:center;">
            <div style="color:#888;font-size:.85em;">% Above 200-Day MA</div>
            <div style="font-size:1.6em;font-weight:bold;color:{_c200};">
            {f"{pct200*100:.0f}%" if pct200 is not None else "—"}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with bc2:
        _cadr = "#27ae60" if (ad_r or 0) >= 0.55 else "#c0392b"
        st.markdown(
            f"""<div style="border:1px solid {_cadr};border-radius:6px;
            padding:10px;text-align:center;">
            <div style="color:#888;font-size:.85em;">Advance / Decline</div>
            <div style="font-size:1.6em;font-weight:bold;color:{_cadr};">
            {f"{adv}↑  {dec}↓" if adv is not None else "—"}</div>
            <div style="font-size:.85em;color:#888;">
            A/D Ratio: {f"{ad_r:.2f}" if ad_r else "—"}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with bc3:
        _bsc = "#27ae60" if breadth["score"] > 0 else "#c0392b"
        st.markdown(
            f"""<div style="border:1px solid {_bsc};border-radius:6px;
            padding:10px;text-align:center;">
            <div style="color:#888;font-size:.85em;">Breadth Score</div>
            <div style="font-size:1.6em;font-weight:bold;color:{_bsc};">
            {breadth['score']:+.3f}</div>
            <div style="font-size:.85em;color:#888;">Signal modifier active</div>
            </div>""",
            unsafe_allow_html=True,
        )
    st.caption("25-stock S&P 500 proxy basket · Refreshes every 4 hours")

except Exception as _breadth_err:
    st.warning(f"Market breadth data unavailable: {_breadth_err}")

st.divider()

# ── Cross-Asset (Intermarket) Signal ──────────────────────────────────
try:
    im = get_intermarket_signal()
    _im_colors = {
        "RISK_ON":  ("#c8f7c5", "#1e8449", "✅"),
        "NEUTRAL":  ("#e8f4f8", "#2980b9", "🔵"),
        "RISK_OFF": ("#ffcccc", "#c0392b", "🔴"),
    }
    im_bg, im_fg, im_icon = _im_colors.get(im["regime"], _im_colors["NEUTRAL"])
    st.markdown(
        f"""<div style="background:{im_bg};border-left:5px solid {im_fg};
        padding:12px 18px;border-radius:6px;margin-bottom:8px;">
        <b style="color:{im_fg};font-size:1.1em;">{im_icon} Cross-Asset Regime: {im['regime']}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;Score: <b>{im['score']:+.3f}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;Sources: <b>{len(im['fetched_assets'])}/5</b>
        </div>""",
        unsafe_allow_html=True,
    )

    im_cols = st.columns(5)
    _im_assets = [
        ("BTC",  im.get("btc_20d"),  "₿ BTC"),
        ("DXY",  im.get("dxy_20d"),  "💵 DXY"),
        ("Gold", im.get("gold_20d"), "🥇 Gold"),
        ("Oil",  im.get("oil_20d"),  "🛢️ Oil"),
        ("TLT",  im.get("tlt_20d"),  "📊 TLT"),
    ]
    for col, (name, ret20, label) in zip(im_cols, _im_assets):
        with col:
            if ret20 is not None:
                c = "#27ae60" if ret20 > 0 else "#c0392b"
                score = im["component_scores"].get(name, 0)
                st.markdown(
                    f"""<div style="border:1px solid {c};border-radius:6px;
                    padding:8px;text-align:center;">
                    <div style="font-size:.8em;color:#888;">{label}</div>
                    <div style="font-size:1.2em;font-weight:bold;color:{c};">
                    {ret20:+.1f}%</div>
                    <div style="font-size:.75em;color:#888;">20d · score {score:+.2f}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.caption(f"{label}\n—")
    st.caption("Cross-asset 20-day returns · Refreshes every 4 hours")

except Exception as _im_err:
    st.warning(f"Cross-asset data unavailable: {_im_err}")

st.divider()

# ── Fear & Greed Index ─────────────────────────────────────────────────
try:
    stock_fg = get_fear_greed_signal("stock")
    crypto_fg = get_fear_greed_signal("crypto")

    _fg_colors = {
        "Extreme Fear":  ("#c8f7c5", "#1e8449", "😱"),
        "Fear":          ("#d4edda", "#27ae60", "😟"),
        "Neutral":       ("#e8f4f8", "#2980b9", "😐"),
        "Greed":         ("#fff3cd", "#e67e22", "🤑"),
        "Extreme Greed": ("#ffcccc", "#c0392b", "🚨"),
    }

    fg_c1, fg_c2 = st.columns(2)
    for col, fg, title in [(fg_c1, stock_fg, "Stocks"), (fg_c2, crypto_fg, "Crypto")]:
        with col:
            label = fg.get("fg_label", "Neutral")
            idx   = fg.get("fg_index", 50)
            score = fg.get("score", 0.0)
            src   = fg.get("source", "—")
            _bg, _fg_c, _icon = _fg_colors.get(label, _fg_colors["Neutral"])
            st.markdown(
                f"""<div style="background:{_bg};border:2px solid {_fg_c};
                border-radius:10px;padding:14px;text-align:center;">
                <div style="font-size:.85em;color:#888;margin-bottom:4px;">
                {_icon} {title} Fear & Greed</div>
                <div style="font-size:2.2em;font-weight:bold;color:{_fg_c};">
                {idx:.0f}</div>
                <div style="font-size:1em;font-weight:bold;color:{_fg_c};">
                {label}</div>
                <div style="font-size:.8em;color:#888;margin-top:4px;">
                Contrarian signal: <b>{score:+.3f}</b> · {src}</div>
                </div>""",
                unsafe_allow_html=True,
            )
    st.caption("0 = Extreme Fear (contrarian bullish) · 100 = Extreme Greed (contrarian bearish) · "
               "Refreshes every 4 hours")

except Exception as _fg_err:
    st.warning(f"Fear & Greed data unavailable: {_fg_err}")

st.divider()

# ── Sector Rotation ────────────────────────────────────────────────────
try:
    sector_overview = get_sector_rotation_overview()
    if sector_overview:
        st.subheader("🔄 Sector Rotation")
        # Sort by score descending
        sorted_sectors = sorted(sector_overview.items(), key=lambda x: x[1]["score"], reverse=True)

        _sr_regime_colors = {
            "LEADING": ("#d4edda", "#27ae60"),
            "NEUTRAL": ("#e8f4f8", "#2980b9"),
            "LAGGING": ("#ffcccc", "#c0392b"),
        }

        # Show in a 4-column grid
        for row_start in range(0, len(sorted_sectors), 4):
            row_sectors = sorted_sectors[row_start:row_start + 4]
            cols = st.columns(4)
            for col, (name, data) in zip(cols, row_sectors):
                with col:
                    bg, fg = _sr_regime_colors.get(data["regime"], ("#f0f0f0", "#7f8c8d"))
                    icon = "▲" if data["regime"] == "LEADING" else "▼" if data["regime"] == "LAGGING" else "━"
                    st.markdown(
                        f"""<div style="background:{bg};border-left:4px solid {fg};
                        border-radius:5px;padding:8px 10px;margin-bottom:6px;">
                        <div style="font-size:.8em;color:#555;">{data['ticker']}</div>
                        <div style="font-weight:bold;font-size:.9em;">{name}</div>
                        <div style="color:{fg};font-size:1.1em;font-weight:bold;">
                        {icon} {data['score']:+.3f}</div>
                        <div style="font-size:.75em;color:#777;">
                        1M: {data['rs_1m']:+.1f}%&nbsp;&nbsp;3M: {data['rs_3m']:+.1f}%</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
        st.caption("Relative strength vs SPY (1M/3M/6M weighted) · 4-hour cached")
    else:
        st.info("Sector rotation data unavailable.")
except Exception as _sr_err:
    st.warning(f"Sector rotation data unavailable: {_sr_err}")

st.divider()

# ── Top Index / Crypto Prices ─────────────────────────────────────────
st.subheader(t("market_snapshot"))
index_symbols = ["SPY", "QQQ", "DIA"]
crypto_symbols = ["BTC/USDT", "ETH/USDT"]

col_count = len(index_symbols) + len(crypto_symbols)
cols = st.columns(col_count)

with st.spinner(t("fetching")):
    # Fetch all snapshot prices in parallel — get_current_price has no rate limiter
    with ThreadPoolExecutor(max_workers=len(index_symbols) + len(crypto_symbols)) as ex:
        index_futures  = {sym: ex.submit(get_current_price, sym) for sym in index_symbols}
        crypto_futures = {sym: ex.submit(get_crypto_price, sym)   for sym in crypto_symbols}

    for i, sym in enumerate(index_symbols):
        with cols[i]:
            data = index_futures[sym].result()
            if data:
                price_card(sym, data["price"], data["change"], data["change_pct"])
            else:
                st.metric(sym, "—", "—")

    for i, sym in enumerate(crypto_symbols):
        with cols[len(index_symbols) + i]:
            # Prefer WebSocket live data, fallback to REST result
            data = get_live_price(sym) or crypto_futures[sym].result()
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
        with ThreadPoolExecutor(max_workers=len(DEFAULT_STOCKS)) as ex:
            stock_results = list(ex.map(get_current_price, DEFAULT_STOCKS))
        stock_data = [r for r in stock_results if r is not None]
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
        with ThreadPoolExecutor(max_workers=len(DEFAULT_CRYPTO)) as ex:
            crypto_results = list(ex.map(get_crypto_price, DEFAULT_CRYPTO))
        crypto_data = [r for r in crypto_results if r is not None]
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
