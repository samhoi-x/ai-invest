"""KPI metric card components."""

import streamlit as st


def price_card(symbol: str, price: float, change: float, change_pct: float):
    """Display a price metric card."""
    # "normal": positive delta → green, negative delta → red (correct for prices)
    # "inverse" would show price drops as green — wrong.
    st.metric(
        label=symbol,
        value=f"${price:,.2f}",
        delta=f"{change:+.2f} ({change_pct:+.2f}%)",
        delta_color="normal",
    )


def signal_card(symbol: str, direction: str, confidence: float,
                strength: float, tech_score: float = 0, sent_score: float = 0,
                ml_score: float = 0, summary: str = ""):
    """Display a large signal card with factor breakdown and optional summary."""
    color_map = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
    icon = color_map.get(direction, "⚪")

    summary_html = ""
    if summary:
        summary_html = f'<p style="margin:8px 0 0 0; font-size:0.95em; opacity:0.9;">{summary}</p>'

    st.markdown(f"""
    <div style="padding:16px; border-radius:12px; border:2px solid {'#26a69a' if direction=='BUY' else '#ef5350' if direction=='SELL' else '#FFC107'};
    background: {'rgba(38,166,154,0.1)' if direction=='BUY' else 'rgba(239,83,80,0.1)' if direction=='SELL' else 'rgba(255,193,7,0.1)'};">
        <h2 style="margin:0;">{icon} {symbol} — {direction}</h2>
        <p style="margin:4px 0;">Confidence: <b>{confidence:.0%}</b> | Strength: <b>{strength:+.2f}</b></p>
        <hr style="margin:8px 0;">
        <small>Technical: {tech_score:+.2f} | Sentiment: {sent_score:+.2f} | ML: {ml_score:+.2f}</small>
        {summary_html}
    </div>
    """, unsafe_allow_html=True)


def risk_metric(label: str, value: str, status: str = "normal"):
    """Display a risk metric with color coding."""
    color = {"good": "#26a69a", "warning": "#FFC107", "danger": "#ef5350", "normal": "#90A4AE"}
    st.markdown(f"""
    <div style="padding:12px; border-radius:8px; border-left:4px solid {color.get(status, color['normal'])}; background:rgba(255,255,255,0.05);">
        <small style="color:#90A4AE;">{label}</small><br>
        <b style="font-size:1.3em;">{value}</b>
    </div>
    """, unsafe_allow_html=True)
