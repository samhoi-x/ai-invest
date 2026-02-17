"""Strategy Backtest - Configuration, equity curve, trade log."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from i18n import t

from data.stock_fetcher import fetch_stock_data
from data.crypto_fetcher import fetch_crypto_data
from strategy.backtester import BacktestEngine
from db.models import save_backtest, get_backtest_results
from dashboard.components.charts import line_chart, bar_chart

st.title(f"\U0001f4c8 {t('backtest')}")

st.warning("⚠️ Backtest results do not guarantee future performance. Subject to survivorship bias and overfitting.")

# ── Configuration ─────────────────────────────────────────────────────
with st.form("backtest_config"):
    st.subheader(t("backtest_params"))
    col1, col2 = st.columns(2)

    with col1:
        symbols_str = st.text_input("Symbols (comma-separated)", "AAPL, MSFT, SPY")
        initial_capital = st.number_input("Initial Capital ($)", value=100000, step=10000, min_value=1000)
        position_size = st.slider("Position Size (%)", 5, 30, 10) / 100

    with col2:
        default_start = datetime.now() - timedelta(days=730)
        start_date = st.date_input("Start Date", value=default_start)
        end_date = st.date_input("End Date", value=datetime.now())
        commission = st.number_input("Commission (%)", value=0.1, step=0.01, min_value=0.0) / 100

    backtest_name = st.text_input("Backtest Name", f"Backtest {datetime.now().strftime('%Y%m%d_%H%M')}")
    run_bt = st.form_submit_button(f"🚀 {t('run_backtest')}", type="primary")

# ── Run Backtest ──────────────────────────────────────────────────────
if run_bt:
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

    if not symbols:
        st.error("Please enter at least one symbol.")
        st.stop()

    with st.spinner("Fetching historical data..."):
        price_data = {}
        for sym in symbols:
            try:
                if "/" in sym:
                    df = fetch_crypto_data(sym, days=(end_date - start_date).days + 30)
                else:
                    period_map = {365: "1y", 730: "2y", 1825: "5y"}
                    days = (end_date - start_date).days
                    period = "2y" if days <= 730 else "5y"
                    df = fetch_stock_data(sym, period=period)

                if df is not None and not df.empty:
                    # Filter to date range
                    mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
                    df_filtered = df[mask]
                    if not df_filtered.empty:
                        price_data[sym] = df_filtered
            except Exception as e:
                st.warning(f"Could not fetch {sym}: {e}")

        if not price_data:
            st.error("No data available for the selected symbols and date range.")
            st.stop()

    with st.spinner("Running backtest..."):
        engine = BacktestEngine(
            initial_capital=initial_capital,
            position_size_pct=position_size,
            commission=commission,
        )
        results = engine.run(price_data)

    if "error" in results:
        st.error(results["error"])
        st.stop()

    # ── Performance Metrics ───────────────────────────────────────────
    st.divider()
    st.subheader(t("performance_summary"))

    mcols = st.columns(4)
    mcols[0].metric("Total Return", f"{results['total_return']:.2%}")
    mcols[1].metric("Annual Return", f"{results['annual_return']:.2%}")
    mcols[2].metric("Sharpe Ratio", f"{results['sharpe_ratio']:.2f}")
    mcols[3].metric("Max Drawdown", f"{results['max_drawdown']:.2%}")

    mcols2 = st.columns(4)
    mcols2[0].metric("Win Rate", f"{results['win_rate']:.1%}")
    mcols2[1].metric("Total Trades", str(results["total_trades"]))
    mcols2[2].metric("Profit Factor", f"{results['profit_factor']:.2f}")
    mcols2[3].metric("Final Value", f"${results['final_value']:,.0f}")

    # ── Equity Curve ──────────────────────────────────────────────────
    st.divider()
    st.subheader(t("equity_curve"))

    eq_df = pd.DataFrame({
        "date": pd.to_datetime(results["dates"]),
        "Strategy": results["equity_curve"],
    })
    if results.get("benchmark"):
        eq_df["Buy & Hold"] = results["benchmark"][:len(eq_df)]

    eq_df = eq_df.set_index("date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq_df.index, y=eq_df["Strategy"],
                             name="Strategy", line=dict(color="#2196F3", width=2)))
    if "Buy & Hold" in eq_df.columns:
        fig.add_trace(go.Scatter(x=eq_df.index, y=eq_df["Buy & Hold"],
                                 name="Buy & Hold", line=dict(color="#FF9800", width=2, dash="dash")))

    fig.update_layout(
        height=500, template="plotly_dark",
        yaxis_title="Portfolio Value ($)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=20, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Drawdown Chart ────────────────────────────────────────────────
    import numpy as np
    eq_arr = np.array(results["equity_curve"])
    peak = np.maximum.accumulate(eq_arr)
    drawdown = (peak - eq_arr) / peak * -100

    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=pd.to_datetime(results["dates"]), y=drawdown,
        fill="tozeroy", name="Drawdown",
        line=dict(color="#ef5350"), fillcolor="rgba(239,83,80,0.3)",
    ))
    fig_dd.update_layout(
        height=300, template="plotly_dark",
        yaxis_title="Drawdown (%)",
        margin=dict(l=50, r=20, t=20, b=20),
    )
    st.plotly_chart(fig_dd, use_container_width=True)

    # ── Trade Log ─────────────────────────────────────────────────────
    st.divider()
    st.subheader(t("trade_log"))

    if results.get("trades"):
        trades_df = pd.DataFrame(results["trades"])
        st.dataframe(trades_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No trades executed.")

    # Save results
    save_backtest(
        name=backtest_name,
        config={"symbols": symbols, "start": str(start_date), "end": str(end_date),
                "capital": initial_capital, "position_size": position_size},
        total_return=results["total_return"],
        annual_return=results["annual_return"],
        sharpe_ratio=results["sharpe_ratio"],
        max_drawdown=results["max_drawdown"],
        win_rate=results["win_rate"],
        total_trades=results["total_trades"],
        equity_curve=results["equity_curve"],
    )
    st.success(f"Backtest '{backtest_name}' saved.")

# ── Past Backtests ────────────────────────────────────────────────────
st.divider()
st.subheader(t("prev_backtests"))

past = get_backtest_results(10)
if past:
    summary = pd.DataFrame([{
        "Name": r["name"],
        "Return": f"{r['total_return']:.2%}",
        "Annual": f"{r['annual_return']:.2%}",
        "Sharpe": f"{r['sharpe_ratio']:.2f}",
        "Max DD": f"{r['max_drawdown']:.2%}",
        "Win Rate": f"{r['win_rate']:.1%}",
        "Trades": r["total_trades"],
        "Date": r["created_at"][:10],
    } for r in past])
    st.dataframe(summary, use_container_width=True, hide_index=True)
else:
    st.caption("No backtests saved yet.")
