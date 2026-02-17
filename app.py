"""AI Smart Investment System - Main Entry Point."""

import streamlit as st
from config import PAGE_ICON, PAGE_TITLE

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title(f"{PAGE_ICON} AI Smart Invest")
    st.caption("Intelligent Investment Analysis System")
    st.divider()

# ── Page Navigation ───────────────────────────────────────────────────
pages = {
    "Market Overview": [
        st.Page("dashboard/pages/1_market_overview.py", title="Market Overview", icon="🌐"),
    ],
    "AI Analysis": [
        st.Page("dashboard/pages/2_ai_signals.py", title="AI Signals", icon="🤖"),
        st.Page("dashboard/pages/3_portfolio.py", title="Portfolio", icon="💼"),
        st.Page("dashboard/pages/4_risk_monitor.py", title="Risk Monitor", icon="🛡️"),
    ],
    "Evaluation": [
        st.Page("dashboard/pages/5_backtest.py", title="Backtest", icon="📈"),
        st.Page("dashboard/pages/6_performance.py", title="Performance", icon="📊"),
    ],
    "System": [
        st.Page("dashboard/pages/7_settings.py", title="Settings", icon="⚙️"),
    ],
}

pg = st.navigation(pages)
pg.run()
