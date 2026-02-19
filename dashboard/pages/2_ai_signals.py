"""AI Trading Signals - Multi-factor signal cards, breakdown, history."""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from i18n import t, get_lang

from data.stock_fetcher import fetch_stock_data
from data.crypto_fetcher import fetch_crypto_data
from data.news_fetcher import fetch_news
from data.social_fetcher import fetch_reddit_posts
from data.stocktwits_fetcher import fetch_stocktwits_posts
from analysis.fear_greed import get_fear_greed_signal
from data.cache_manager import cache_price_data, get_cached_price_data
from analysis.technical import compute_technical_signal, compute_all_indicators, atr as calc_atr
from analysis.sentiment import compute_sentiment_signal
from analysis.ml_models import compute_ml_signal
from analysis.multi_timeframe import compute_mtf_signal
from analysis.earnings_filter import get_earnings_filter
from analysis.analyst_consensus import get_analyst_consensus
from analysis.market_breadth import get_market_breadth
from strategy.signal_combiner import combine_signals
from strategy.signal_explainer import explain_signal
from strategy.risk_manager import generate_action_plan
from dashboard.components.metrics_cards import signal_card
from dashboard.components.signal_display import (
    factor_breakdown, signal_table, signal_explanation_panel, action_plan_panel,
)
from dashboard.components.charts import candlestick_chart, line_chart
from db.models import save_signal, get_latest_signals, get_signal_history, get_holdings, get_setting
from data.notifier import notify_signal
from config import DEFAULT_STOCKS, DEFAULT_CRYPTO

st.title(f"\U0001f916 {t('ai_signals')}")

st.warning(f"⚠️ {t('disclaimer')}")

# ── Symbol Selection ──────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])
with col1:
    asset_type = st.radio(t("asset_type"), [t("stock"), t("crypto")], horizontal=True, key="sig_type")
with col2:
    if asset_type == t("stock"):
        symbol = st.selectbox(t("select_symbol"), DEFAULT_STOCKS, key="sig_symbol")
    else:
        symbol = st.selectbox(t("select_symbol"), DEFAULT_CRYPTO, key="sig_crypto")

generate = st.button(f"🔄 {t('generate_signal')}", type="primary", use_container_width=True)

# ── Signal Generation ─────────────────────────────────────────────────
if generate:
    with st.spinner(f"{t('analyzing')} {symbol}..."):
        # 1. Fetch price data
        try:
            if asset_type == t("stock"):
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

        # 2. Technical analysis — compute indicators once and reuse for the chart
        st.info("Computing technical indicators...")
        indicators_df = compute_all_indicators(df)
        tech_signal = compute_technical_signal(df, _indicators=indicators_df)

        # 3. Sentiment analysis
        st.info("Analyzing market sentiment...")
        try:
            news = fetch_news(symbol.split("/")[0])
            reddit_posts = fetch_reddit_posts(
                symbol.split("/")[0],
                "crypto" if asset_type == t("crypto") else "stock",
            )
            social = [p["title"] + " " + p.get("text", "") for p in reddit_posts]
            # StockTwits: real-time retail sentiment (no auth required)
            social.extend(fetch_stocktwits_posts(symbol))
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

        # 4b. Multi-timeframe confluence
        st.info("Checking multi-timeframe alignment...")
        try:
            _atype = "crypto" if asset_type == t("crypto") else "stock"
            mtf_signal = compute_mtf_signal(symbol, _atype, df)
        except Exception:
            mtf_signal = None

        # 4c. Earnings proximity filter (stocks only)
        earnings_filter = None
        if asset_type != t("crypto"):
            try:
                earnings_filter = get_earnings_filter(symbol)
            except Exception:
                earnings_filter = None

        # 4d. Analyst consensus + market breadth + intermarket (global)
        analyst_signal = None
        if asset_type != t("crypto"):
            try:
                analyst_signal = get_analyst_consensus(symbol)
            except Exception:
                analyst_signal = None

        try:
            breadth_signal = get_market_breadth()
        except Exception:
            breadth_signal = None

        try:
            from analysis.intermarket import get_intermarket_signal
            intermarket_signal = get_intermarket_signal()
        except Exception:
            intermarket_signal = None

        try:
            _atype_str = "crypto" if asset_type == t("crypto") else "stock"
            fear_greed_signal = get_fear_greed_signal(_atype_str)
        except Exception:
            fear_greed_signal = None

        # 4e. Sector rotation (4-hour cached sector overview)
        st.info("Checking sector rotation...")
        try:
            from analysis.sector_rotation import get_sector_signal
            _atype_str = "crypto" if asset_type == t("crypto") else "stock"
            sector_signal = get_sector_signal(symbol, _atype_str)
        except Exception:
            sector_signal = None

        # 4f. Short interest / squeeze detector (24-hour cached)
        st.info("Fetching short interest data...")
        try:
            from analysis.short_interest import get_short_interest_signal
            _atype_str = "crypto" if asset_type == t("crypto") else "stock"
            short_interest_signal = get_short_interest_signal(symbol, _atype_str, df)
        except Exception:
            short_interest_signal = None

        # 4g. Options market sentiment (put/call + IV skew; 2-hour cached)
        st.info("Fetching options market data...")
        try:
            from analysis.options_signal import get_options_signal
            _atype_str = "crypto" if asset_type == t("crypto") else "stock"
            options_signal = get_options_signal(symbol, _atype_str)
        except Exception:
            options_signal = None

        # 5. Combine signals
        combined = combine_signals(
            tech_signal, sent_signal, ml_signal,
            mtf=mtf_signal,
            earnings_filter=earnings_filter,
            breadth=breadth_signal,
            analyst=analyst_signal,
            intermarket=intermarket_signal,
            fear_greed=fear_greed_signal,
            sector=sector_signal,
            short_interest=short_interest_signal,
            options=options_signal,
        )
        combined["symbol"] = symbol

        # 6. Generate beginner-friendly explanation
        explanations = explain_signal(combined, tech_signal, lang=get_lang())

        # 7. Generate action plan
        current_price = df["close"].iloc[-1]
        atr_series = calc_atr(df)
        atr_val = atr_series.iloc[-1] if not atr_series.empty else None
        if atr_val is not None and pd.isna(atr_val):
            atr_val = None

        portfolio_value = get_setting("portfolio_value_default", 100000)
        if portfolio_value is None:
            portfolio_value = 100000
        cash = get_setting("available_cash", portfolio_value)
        if cash is None:
            cash = portfolio_value

        action_plan = generate_action_plan(
            symbol, combined, current_price, atr_val,
            portfolio_value, cash,
            asset_type="crypto" if asset_type == t("crypto") else "stock",
        )

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

        # Send Telegram notification (if configured)
        if combined["direction"] in ("BUY", "SELL"):
            notify_signal(symbol, combined)

    # ── Display Results ───────────────────────────────────────────────
    st.divider()

    # Earnings warning banner (shown before signal card if relevant)
    if combined.get("earnings_warning"):
        days = earnings_filter.get("days_to_earnings", 0) if earnings_filter else 0
        if days == 0:
            st.error(f"🚨 {combined['earnings_warning']}")
        else:
            st.warning(f"📅 {combined['earnings_warning']}")

    # Signal card (with plain-language summary)
    signal_card(symbol, combined["direction"], combined["confidence"],
                combined["strength"], combined["technical_score"],
                combined["sentiment_score"], combined["ml_score"],
                summary=explanations["summary"])

    # Action plan
    st.divider()
    action_plan_panel(action_plan, lang=get_lang())

    # Factor breakdown (with tooltips)
    st.divider()
    st.subheader(t("factor_breakdown"))
    factor_breakdown(combined["technical_score"], combined["sentiment_score"],
                     combined["ml_score"])

    # Beginner-friendly explanation (expandable)
    with st.expander(f"💡 {t('why_this_signal')}"):
        signal_explanation_panel(explanations)

    # Adaptive thresholds panel
    thresholds = combined.get("thresholds", {})
    if thresholds.get("adjustments"):
        with st.expander("⚙️ Adaptive Thresholds"):
            bt = thresholds.get("buy", 0.30)
            bb = thresholds.get("base_buy", 0.30)
            st.markdown(
                f"**BUY threshold:** {bt:.2f} "
                f"<span style='color:#90A4AE;'>(base {bb:.2f})</span>  |  "
                f"**Conf min:** {thresholds.get('buy_conf_min', 0.65):.2f}",
                unsafe_allow_html=True,
            )
            for adj in thresholds["adjustments"]:
                st.caption(f"• {adj}")

    # Technical details (for advanced users)
    with st.expander(f"📊 {t('tech_details')}"):
        st.json(tech_signal)

    with st.expander(f"📰 {t('sent_details')}"):
        st.write(f"News articles analyzed: {sent_signal.get('news_count', 0)}")
        st.write(f"Social posts analyzed: {sent_signal.get('social_count', 0)} "
                 f"(Reddit + StockTwits)")
        st.write(f"News sentiment: {sent_signal.get('news_sentiment', 0):+.4f}")
        st.write(f"Social sentiment: {sent_signal.get('social_sentiment', 0):+.4f}")
        # Fear & Greed
        if combined.get("fg_index") is not None:
            fg_color = ("#27ae60" if combined["fg_label"] in ("Extreme Fear", "Fear")
                        else "#c0392b" if combined["fg_label"] in ("Extreme Greed", "Greed")
                        else "#e67e22")
            st.markdown(
                f"**Fear & Greed Index:** "
                f"<span style='color:{fg_color};font-weight:bold;'>"
                f"{combined['fg_index']:.0f} — {combined['fg_label']}</span>  "
                f"(contrarian signal: {combined['fg_score']:+.3f})",
                unsafe_allow_html=True,
            )

    with st.expander(f"🤖 {t('ml_details')}"):
        # Show per-model scores including Transformer
        ml_rows = []
        for model_key, label in [("xgboost","XGBoost"),("lightgbm","LightGBM"),
                                  ("lstm","LSTM"),("transformer","Transformer")]:
            m = ml_signal.get(model_key, {})
            if m and "signal_score" in m:
                row = {"Model": label,
                       "Score": f"{m['signal_score']:+.3f}",
                       "Confidence": f"{m.get('confidence',0)*100:.0f}%"}
                if model_key == "transformer" and m.get("horizon_preds"):
                    hp = m["horizon_preds"]
                    row["1d"] = f"{hp.get('1d',0):+.3f}"
                    row["5d"] = f"{hp.get('5d',0):+.3f}"
                    row["10d"] = f"{hp.get('10d',0):+.3f}"
                ml_rows.append(row)
        if ml_rows:
            st.dataframe(pd.DataFrame(ml_rows), hide_index=True,
                         use_container_width=True)
        st.json({k: v for k, v in ml_signal.items()
                 if k not in ("xgboost","lightgbm","lstm","transformer")})

    # Analyst consensus panel
    if analyst_signal and analyst_signal.get("total_ratings", 0) > 0:
        with st.expander("🏦 Analyst Consensus"):
            a = analyst_signal
            rating_colors = {
                "Strong Buy": "#1e8449", "Buy": "#27ae60",
                "Hold": "#e67e22", "Sell": "#c0392b", "Strong Sell": "#922b21",
            }
            rc = rating_colors.get(a["rating_label"], "#7f8c8d")
            st.markdown(
                f"**Rating:** <span style='color:{rc};font-weight:bold;'>"
                f"{a['rating_label']}</span>  |  "
                f"**Score:** {a['score']:+.3f}  |  "
                f"**Analysts:** {a['total_ratings']}",
                unsafe_allow_html=True,
            )
            rac1, rac2, rac3 = st.columns(3)
            with rac1:
                st.metric("Buy %", f"{(a['buy_pct'] or 0)*100:.0f}%")
            with rac2:
                st.metric("Hold %", f"{(a['hold_pct'] or 0)*100:.0f}%")
            with rac3:
                st.metric("Sell %", f"{(a['sell_pct'] or 0)*100:.0f}%")
            if a.get("target_price"):
                upside_str = (f"  ({a['target_upside_pct']:+.1f}% upside)"
                              if a.get("target_upside_pct") is not None else "")
                st.markdown(f"**Consensus Target Price:** ${a['target_price']:,.2f}{upside_str}")
            if a.get("recent_upgrades") or a.get("recent_downgrades"):
                st.markdown(
                    f"**Last 30 days:** "
                    f"🟢 {a['recent_upgrades']} upgrades  "
                    f"🔴 {a['recent_downgrades']} downgrades"
                )

    # Multi-timeframe alignment panel
    if mtf_signal and mtf_signal.get("timeframes_available"):
        with st.expander("📐 Multi-Timeframe Alignment"):
            alignment_pct = int(mtf_signal["alignment"] * 100)
            align_color = "#27ae60" if alignment_pct >= 75 else "#e67e22" if alignment_pct >= 50 else "#c0392b"
            st.markdown(
                f"**Alignment:** <span style='color:{align_color};font-weight:bold;'>"
                f"{alignment_pct}%</span>  |  "
                f"**MTF Score:** {mtf_signal['score']:+.3f}  |  "
                f"**Timeframes:** {', '.join(mtf_signal['timeframes_available'])}",
                unsafe_allow_html=True,
            )
            tf_rows = [
                {"Timeframe": tf,
                 "Score": f"{v['score']:+.3f}",
                 "Confidence": f"{v['confidence']*100:.0f}%",
                 "Direction": "🟢 Bullish" if v["score"] > 0.05
                              else "🔴 Bearish" if v["score"] < -0.05
                              else "⚪ Neutral"}
                for tf, v in mtf_signal["tf_scores"].items()
            ]
            if tf_rows:
                st.dataframe(pd.DataFrame(tf_rows), hide_index=True,
                             use_container_width=True)

    # Sector rotation panel
    if sector_signal and sector_signal.get("regime") not in (None, "N/A"):
        with st.expander("🔄 Sector Rotation"):
            sr = sector_signal
            _sr_colors = {"LEADING": "#27ae60", "NEUTRAL": "#2980b9", "LAGGING": "#c0392b"}
            rc = _sr_colors.get(sr["regime"], "#7f8c8d")
            st.markdown(
                f"**Sector:** {sr.get('sector', 'N/A')}  |  "
                f"**Regime:** <span style='color:{rc};font-weight:bold;'>{sr['regime']}</span>  |  "
                f"**Score:** {sr['score']:+.3f}  |  "
                f"**Signal modifier:** {sr.get('modifier', 0.0):+.2f}",
                unsafe_allow_html=True,
            )
            if sr.get("rs_1m") is not None:
                sr_c1, sr_c2, sr_c3 = st.columns(3)
                with sr_c1:
                    st.metric("1-Month RS", f"{sr['rs_1m']:+.2f}%")
                with sr_c2:
                    st.metric("3-Month RS", f"{sr['rs_3m']:+.2f}%")
                with sr_c3:
                    st.metric("6-Month RS", f"{sr['rs_6m']:+.2f}%")
            st.caption("Relative strength vs SPY · 4-hour cached")

    # Options sentiment panel
    if options_signal and options_signal.get("regime") not in (None, "N/A"):
        with st.expander("📊 Options Market Sentiment"):
            op = options_signal
            _op_colors = {
                "FEAR":        "#27ae60",  # extreme fear = contrarian bullish
                "NEUTRAL":     "#2980b9",
                "COMPLACENCY": "#c0392b",  # extreme greed = contrarian bearish
            }
            oc = _op_colors.get(op["regime"], "#7f8c8d")
            _pcr_str = f"{op['pcr']:.2f}" if op.get('pcr') is not None else '—'
            st.markdown(
                f"**Regime:** <span style='color:{oc};font-weight:bold;'>{op['regime']}</span>  |  "
                f"**Score:** {op['score']:+.3f}  |  "
                f"**Put/Call Ratio:** {_pcr_str}",
                unsafe_allow_html=True,
            )
            op_c1, op_c2, op_c3 = st.columns(3)
            with op_c1:
                st.metric("Put/Call Ratio", f"{op['pcr']:.2f}" if op.get("pcr") else "—")
            with op_c2:
                st.metric("Avg Call IV",
                          f"{op['avg_call_iv']*100:.1f}%" if op.get("avg_call_iv") else "—")
            with op_c3:
                st.metric("IV Skew (P/C)",
                          f"{op['iv_skew']:.2f}" if op.get("iv_skew") else "—")
            st.caption(
                "PCR > 1.2 = elevated fear (contrarian bullish) · "
                "PCR < 0.8 = complacency (contrarian bearish) · 2-hour cached"
            )

    # Chart patterns panel
    patterns = tech_signal.get("patterns", [])
    if patterns:
        with st.expander(f"🔍 Chart Patterns ({len(patterns)} detected)"):
            for p in patterns:
                ptype_color = "#27ae60" if p["type"] == "bullish" else "#c0392b"
                st.markdown(
                    f"**{p['name']}** — "
                    f"<span style='color:{ptype_color};'>{p['type'].capitalize()}</span>  |  "
                    f"Score: {p['score']:+.3f}  |  {p.get('detail', '')}",
                    unsafe_allow_html=True,
                )

    # Short interest / squeeze panel
    if short_interest_signal and short_interest_signal.get("regime") not in (None, "N/A"):
        with st.expander("📉 Short Interest & Squeeze"):
            si = short_interest_signal
            _si_colors = {
                "SQUEEZE":      "#1e8449",
                "SQUEEZE_BUILD":"#27ae60",
                "HIGH_SHORT":   "#e67e22",
                "BEAR_CONFIRM": "#c0392b",
                "MILD_SQUEEZE": "#27ae60",
                "MILD_CONFIRM": "#e74c3c",
                "MILD":         "#e67e22",
                "NEUTRAL":      "#7f8c8d",
            }
            sc = _si_colors.get(si["regime"], "#7f8c8d")
            sf = si.get("short_float")
            st.markdown(
                f"**Regime:** <span style='color:{sc};font-weight:bold;'>{si['regime']}</span>  |  "
                f"**Score:** {si['score']:+.3f}  |  "
                f"**Short Float:** {f'{sf*100:.1f}%' if sf is not None else '—'}  |  "
                f"**Days-to-Cover:** {si.get('short_ratio') or '—'}",
                unsafe_allow_html=True,
            )
            mom = si.get("momentum_5d")
            if mom is not None:
                mom_color = "#27ae60" if mom > 0 else "#c0392b"
                st.markdown(
                    f"**5-Day Momentum:** "
                    f"<span style='color:{mom_color};font-weight:bold;'>{mom:+.2f}%</span>",
                    unsafe_allow_html=True,
                )
            st.caption("Short interest from yfinance · 24-hour cached")

    # Chart with indicators (reuse indicators_df computed during signal generation)
    st.divider()
    st.subheader(t("price_chart_indicators"))
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
st.subheader(t("recent_signals"))
recent = get_latest_signals(30)
if recent:
    signal_table(recent)
else:
    st.caption(t("no_signals"))
