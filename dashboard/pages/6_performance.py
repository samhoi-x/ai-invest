"""Performance Tracking - Returns, benchmarks, signal accuracy."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db.models import get_latest_signals, get_transactions, get_backtest_results
from dashboard.components.charts import bar_chart, line_chart

st.title("📊 Performance Tracking")

# ── Signal Accuracy ───────────────────────────────────────────────────
st.subheader("Signal Accuracy Statistics")

signals = get_latest_signals(200)
if signals:
    df = pd.DataFrame(signals)

    total = len(df)
    buys = len(df[df["direction"] == "BUY"])
    sells = len(df[df["direction"] == "SELL"])
    holds = len(df[df["direction"] == "HOLD"])

    scols = st.columns(4)
    scols[0].metric("Total Signals", str(total))
    scols[1].metric("BUY Signals", str(buys), f"{buys/total:.0%}" if total > 0 else "0%")
    scols[2].metric("SELL Signals", str(sells), f"{sells/total:.0%}" if total > 0 else "0%")
    scols[3].metric("HOLD Signals", str(holds), f"{holds/total:.0%}" if total > 0 else "0%")

    # Confidence distribution
    st.divider()
    st.subheader("Signal Confidence Distribution")

    if "confidence" in df.columns:
        fig = go.Figure()
        for direction, color in [("BUY", "#26a69a"), ("SELL", "#ef5350"), ("HOLD", "#FFC107")]:
            subset = df[df["direction"] == direction]
            if not subset.empty:
                fig.add_trace(go.Histogram(
                    x=subset["confidence"], name=direction,
                    marker_color=color, opacity=0.7, nbinsx=20,
                ))
        fig.update_layout(
            height=400, template="plotly_dark",
            xaxis_title="Confidence", yaxis_title="Count",
            barmode="overlay",
            margin=dict(l=50, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Signal strength over time
    st.divider()
    st.subheader("Signal Strength Over Time")

    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df = df.sort_values("created_at")

        # Group by symbol
        symbols = df["symbol"].unique()
        selected_sym = st.selectbox("Filter by symbol", ["All"] + list(symbols))

        if selected_sym != "All":
            plot_df = df[df["symbol"] == selected_sym]
        else:
            plot_df = df

        fig_str = go.Figure()
        fig_str.add_trace(go.Scatter(
            x=plot_df["created_at"], y=plot_df["strength"],
            mode="lines+markers", name="Signal Strength",
            line=dict(color="#2196F3"),
            marker=dict(
                color=plot_df["direction"].map({"BUY": "#26a69a", "SELL": "#ef5350", "HOLD": "#FFC107"}),
                size=8,
            ),
        ))
        fig_str.add_hline(y=0.3, line_dash="dash", line_color="#26a69a", annotation_text="BUY threshold")
        fig_str.add_hline(y=-0.2, line_dash="dash", line_color="#ef5350", annotation_text="SELL threshold")
        fig_str.add_hline(y=0, line_color="gray", opacity=0.5)
        fig_str.update_layout(
            height=400, template="plotly_dark",
            yaxis_title="Signal Strength", yaxis_range=[-1.1, 1.1],
            margin=dict(l=50, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_str, use_container_width=True)

    # Factor contribution
    st.divider()
    st.subheader("Factor Contribution Breakdown")

    factor_cols = ["technical_score", "sentiment_score", "ml_score"]
    available_factors = [c for c in factor_cols if c in df.columns]
    if available_factors:
        avg_factors = df[available_factors].mean()
        fig_factors = go.Figure(go.Bar(
            x=[c.replace("_score", "").title() for c in available_factors],
            y=avg_factors.values,
            marker_color=["#FF9800", "#2196F3", "#9C27B0"],
        ))
        fig_factors.update_layout(
            height=350, template="plotly_dark",
            yaxis_title="Average Score",
            margin=dict(l=50, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_factors, use_container_width=True)

else:
    st.info("No signals generated yet. Generate signals on the AI Signals page to see performance data.")

# ── Backtest Performance Comparison ───────────────────────────────────
st.divider()
st.subheader("Backtest Performance Comparison")

backtests = get_backtest_results(10)
if backtests:
    bt_df = pd.DataFrame([{
        "Name": b["name"],
        "Total Return": b["total_return"],
        "Annual Return": b["annual_return"],
        "Sharpe": b["sharpe_ratio"],
        "Max Drawdown": b["max_drawdown"],
    } for b in backtests])

    fig_bt = go.Figure()
    fig_bt.add_trace(go.Bar(
        x=bt_df["Name"], y=bt_df["Total Return"] * 100,
        name="Total Return (%)",
        marker_color="#2196F3",
    ))
    fig_bt.add_trace(go.Bar(
        x=bt_df["Name"], y=bt_df["Max Drawdown"] * -100,
        name="Max Drawdown (%)",
        marker_color="#ef5350",
    ))
    fig_bt.update_layout(
        height=400, template="plotly_dark", barmode="group",
        yaxis_title="Percentage (%)",
        margin=dict(l=50, r=20, t=20, b=20),
    )
    st.plotly_chart(fig_bt, use_container_width=True)
else:
    st.caption("No backtest results available.")

# ── Transaction Summary ───────────────────────────────────────────────
st.divider()
st.subheader("Transaction Summary")

transactions = get_transactions(200)
if transactions:
    tx_df = pd.DataFrame(transactions)
    st.write(f"Total transactions: {len(tx_df)}")

    if "action" in tx_df.columns:
        action_counts = tx_df["action"].value_counts()
        st.write("Action breakdown:")
        for action, count in action_counts.items():
            st.write(f"  - {action}: {count}")
else:
    st.caption("No transactions recorded.")
