"""AI Smart Investment System - Main Entry Point."""

import streamlit as st
from config import PAGE_ICON, PAGE_TITLE
from i18n import t, language_selector
from logger import setup_logging

setup_logging()

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title(f"{PAGE_ICON} {t('app_title')}")
    st.caption(t("app_subtitle"))
    language_selector()
    st.divider()

# ── Daily Briefing in sidebar ─────────────────────────────────────────
try:
    from dashboard.components.daily_briefing import render_daily_briefing
    _lang = st.session_state.get("lang", "zh")
    render_daily_briefing(lang=_lang)
except Exception:
    pass  # never crash the app due to briefing

# ── Page Navigation ───────────────────────────────────────────────────
pages = {
    t("market_overview"): [
        st.Page("dashboard/pages/1_market_overview.py", title=t("market_overview"), icon="\U0001f310"),
    ],
    "AI": [
        st.Page("dashboard/pages/2_ai_signals.py", title=t("ai_signals"), icon="\U0001f916"),
        st.Page("dashboard/pages/3_portfolio.py", title=t("portfolio"), icon="\U0001f4bc"),
        st.Page("dashboard/pages/4_risk_monitor.py", title=t("risk_monitor"), icon="\U0001f6e1\ufe0f"),
    ],
    t("backtest"): [
        st.Page("dashboard/pages/5_backtest.py", title=t("backtest"), icon="\U0001f4c8"),
        st.Page("dashboard/pages/6_performance.py", title=t("performance"), icon="\U0001f4ca"),
    ],
    t("paper_trading"): [
        st.Page("dashboard/pages/9_paper_trading.py", title=t("paper_trading"), icon="\U0001f9ea"),
    ],
    t("settings"): [
        st.Page("dashboard/pages/7_settings.py", title=t("settings"), icon="\u2699\ufe0f"),
    ],
    t("help_guide"): [
        st.Page("dashboard/pages/8_help.py", title=t("help_guide"), icon="\U0001f4d6"),
    ],
}

pg = st.navigation(pages)
pg.run()
