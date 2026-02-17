"""Signal display components."""

import streamlit as st
import pandas as pd


def signal_table(signals: list[dict]):
    """Display a table of trading signals."""
    if not signals:
        st.caption("No signals available.")
        return
    df = pd.DataFrame(signals)
    display_cols = ["symbol", "direction", "strength", "confidence",
                    "technical_score", "sentiment_score", "ml_score", "created_at"]
    available = [c for c in display_cols if c in df.columns]
    df = df[available]

    def color_direction(val):
        if val == "BUY":
            return "color: #26a69a; font-weight: bold"
        elif val == "SELL":
            return "color: #ef5350; font-weight: bold"
        return "color: #FFC107"

    if "direction" in df.columns:
        styled = df.style.map(color_direction, subset=["direction"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def factor_breakdown(tech: float, sent: float, ml: float):
    """Show a horizontal breakdown of the three factors."""
    cols = st.columns(3)
    with cols[0]:
        st.metric("Technical", f"{tech:+.2f}")
        st.progress(max(0, min(1, (tech + 1) / 2)))
    with cols[1]:
        st.metric("Sentiment", f"{sent:+.2f}")
        st.progress(max(0, min(1, (sent + 1) / 2)))
    with cols[2]:
        st.metric("ML Model", f"{ml:+.2f}")
        st.progress(max(0, min(1, (ml + 1) / 2)))
