"""Risk Monitor - Drawdown, VaR, position risk, alerts."""

import streamlit as st
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from i18n import t

from data.stock_fetcher import get_current_price, fetch_stock_data
from data.crypto_fetcher import get_crypto_price, fetch_crypto_data
from db.models import get_holdings, get_risk_alerts
from strategy.risk_manager import (
    check_drawdown, check_cash_reserve, calculate_stop_loss,
    compute_portfolio_risk, check_position_limits
)
from analysis.technical import atr as compute_atr
from dashboard.components.charts import line_chart, bar_chart
from dashboard.components.metrics_cards import risk_metric
from config import RISK

st.title(f"\U0001f6e1\ufe0f {t('risk_monitor')}")

# ── Portfolio Risk Overview ───────────────────────────────────────────
holdings = get_holdings()

if not holdings:
    st.info("Add holdings in Portfolio page to see risk analysis.")
    st.stop()


def _fetch_holding_info(h: dict) -> dict:
    """Fetch current price and ATR for one holding (runs in thread pool)."""
    # Price
    if h["asset_type"] == "crypto":
        data = get_crypto_price(h["symbol"])
        try:
            df = fetch_crypto_data(h["symbol"], days=30)
        except Exception:
            df = None
    else:
        data = get_current_price(h["symbol"])
        try:
            df = fetch_stock_data(h["symbol"], period="1mo")
        except Exception:
            df = None

    price = data["price"] if data else h["avg_cost"]

    atr_val = None
    if df is not None and not df.empty:
        try:
            atr_val = compute_atr(df).iloc[-1]
            if pd.isna(atr_val):
                atr_val = None
        except Exception:
            pass

    return {"symbol": h["symbol"], "price": price, "atr": atr_val}


# Parallel fetch: price + ATR for every holding in one pass
with ThreadPoolExecutor(max_workers=min(len(holdings), 8)) as ex:
    fetch_results = list(ex.map(_fetch_holding_info, holdings))

fetch_map = {r["symbol"]: r for r in fetch_results}
prices = {r["symbol"]: r["price"] for r in fetch_results}
total_value = sum(h["quantity"] * fetch_map[h["symbol"]]["price"] for h in holdings)

# Simulate equity curve (from holdings cost to current value)
total_cost = sum(h["quantity"] * h["avg_cost"] for h in holdings)
equity_curve = [total_cost, total_value]  # Simplified

dd_info = check_drawdown(equity_curve)
cash_reserve = total_value * RISK["min_cash_reserve"]  # Assumed
cash_info = check_cash_reserve(cash_reserve, total_value)

# ── Risk Metric Cards ────────────────────────────────────────────────
st.subheader(t("risk_overview"))
rcols = st.columns(4)

with rcols[0]:
    dd_status = "good" if dd_info["current_drawdown"] < 0.05 else "warning" if dd_info["current_drawdown"] < 0.12 else "danger"
    risk_metric("Current Drawdown", f"{dd_info['current_drawdown']:.1%}", dd_status)

with rcols[1]:
    risk_metric("Max Drawdown", f"{dd_info['max_drawdown']:.1%}",
                "good" if dd_info["max_drawdown"] < 0.10 else "warning")

with rcols[2]:
    risk_metric("Drawdown Status", dd_info["status"],
                {"OK": "good", "WARNING": "warning", "HALT": "danger", "CRITICAL": "danger"}.get(dd_info["status"], "normal"))

with rcols[3]:
    risk_metric("Cash Reserve", f"{cash_info['cash_pct']:.1%}",
                "good" if cash_info["ok"] else "danger")

# ── Drawdown Protection Rules ────────────────────────────────────────
st.divider()
st.subheader(t("drawdown_protection"))

if dd_info["actions"]:
    for action in dd_info["actions"]:
        st.warning(f"⚠️ {action}")
else:
    st.success("All drawdown levels within normal range.")

# Rule visualization
dd_levels = pd.DataFrame([
    {"Level": "Warning (8%)", "Threshold": 0.08, "Action": "New positions halved"},
    {"Level": "Halt (12%)", "Threshold": 0.12, "Action": "Stop all new buys"},
    {"Level": "Reduce (15%)", "Threshold": 0.15, "Action": "Reduce 25%, move to cash"},
])
st.dataframe(dd_levels, use_container_width=True, hide_index=True)

# ── Position Risk Table ──────────────────────────────────────────────
st.divider()
st.subheader(t("position_risk"))

position_risks = []
for h in holdings:
    price = prices.get(h["symbol"], h["avg_cost"])
    market_val = h["quantity"] * price
    weight = market_val / total_value if total_value > 0 else 0
    pnl_pct = (price / h["avg_cost"] - 1) * 100

    # Reuse ATR already fetched in parallel above
    atr_val = fetch_map[h["symbol"]]["atr"]
    stops = calculate_stop_loss(h["avg_cost"], atr_val)

    position_risks.append({
        "Symbol": h["symbol"],
        "Type": h["asset_type"],
        "Weight": f"{weight:.1%}",
        "P&L": f"{pnl_pct:+.1f}%",
        "Stop (ATR)": f"${stops['atr_stop']}" if stops["atr_stop"] else "N/A",
        "Stop (Pct)": f"${stops['pct_stop']}",
        "Stop (Trail)": f"${stops['trailing_stop']}",
        "Recommended Stop": f"${stops['recommended']}",
    })

st.dataframe(pd.DataFrame(position_risks), use_container_width=True, hide_index=True)

# ── Risk Limit Checks ────────────────────────────────────────────────
st.divider()
st.subheader(t("risk_limit_status"))

current_crypto_value = sum(
    h["quantity"] * prices[h["symbol"]]
    for h in holdings if h["asset_type"] == "crypto"
)

limits = []
for h in holdings:
    price = prices.get(h["symbol"], h["avg_cost"])
    val = h["quantity"] * price
    check = check_position_limits(h["symbol"], val, total_value, h["asset_type"],
                                  current_crypto_value=current_crypto_value)
    status = "✅" if check["allowed"] else "❌"
    limits.append({
        "Symbol": h["symbol"],
        "Value": f"${val:,.0f}",
        "Weight": f"{val/total_value:.1%}" if total_value > 0 else "0%",
        "Status": status,
        "Issues": "; ".join(check["violations"] + check["warnings"]) or "None",
    })

st.dataframe(pd.DataFrame(limits), use_container_width=True, hide_index=True)

# ── Risk Alerts ───────────────────────────────────────────────────────
st.divider()
st.subheader(t("risk_alerts"))
alerts = get_risk_alerts(30)
if alerts:
    for alert in alerts:
        severity_icon = {"critical": "🔴", "high": "🟠", "warning": "🟡", "info": "🔵"}.get(
            alert["severity"], "⚪")
        st.markdown(f"{severity_icon} **{alert['alert_type']}** | {alert['message']} | {alert['created_at']}")
else:
    st.caption("No recent alerts.")
