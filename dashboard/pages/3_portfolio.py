"""Portfolio Management - Holdings, allocation, optimization."""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data.stock_fetcher import get_current_price, fetch_stock_data
from data.crypto_fetcher import get_crypto_price
from db.models import get_holdings, upsert_holding, remove_holding, add_transaction, get_transactions
from strategy.portfolio_optimizer import optimize_portfolio, get_rebalance_suggestions, build_returns_from_prices
from dashboard.components.charts import pie_chart
from dashboard.components.tables import holdings_table, transaction_table
from config import DEFAULT_STOCKS, DEFAULT_CRYPTO

st.title("💼 Portfolio Management")

# ── Add Holdings ──────────────────────────────────────────────────────
with st.expander("➕ Add/Update Holding"):
    with st.form("add_holding"):
        hcol1, hcol2, hcol3 = st.columns(3)
        with hcol1:
            h_asset_type = st.selectbox("Type", ["stock", "crypto"])
            if h_asset_type == "stock":
                h_symbol = st.selectbox("Symbol", DEFAULT_STOCKS, key="hold_sym")
            else:
                h_symbol = st.selectbox("Symbol", DEFAULT_CRYPTO, key="hold_crypto")
        with hcol2:
            h_quantity = st.number_input("Quantity", min_value=0.0, step=0.01, value=10.0)
            h_avg_cost = st.number_input("Avg Cost ($)", min_value=0.0, step=0.01, value=100.0)
        with hcol3:
            h_sector = st.text_input("Sector", "Technology")

        submitted = st.form_submit_button("Add/Update", type="primary")
        if submitted:
            upsert_holding(h_symbol, h_asset_type, h_quantity, h_avg_cost, h_sector)
            add_transaction(h_symbol, "BUY", h_quantity, h_avg_cost, "Manual entry")
            st.success(f"Added {h_quantity} {h_symbol} @ ${h_avg_cost}")
            st.rerun()

# ── Portfolio Overview ────────────────────────────────────────────────
holdings = get_holdings()

if not holdings:
    st.info("No holdings yet. Add positions above to get started.")
    st.stop()

# Fetch current prices
prices = {}
total_value = 0
total_cost = 0
for h in holdings:
    sym = h["symbol"]
    if h["asset_type"] == "crypto":
        data = get_crypto_price(sym)
    else:
        data = get_current_price(sym)

    if data:
        prices[sym] = data["price"]
    else:
        prices[sym] = h["avg_cost"]

    market_val = h["quantity"] * prices[sym]
    cost_val = h["quantity"] * h["avg_cost"]
    total_value += market_val
    total_cost += cost_val

day_pnl = total_value - total_cost  # Simplified
total_return = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0

# ── Summary Cards ─────────────────────────────────────────────────────
st.subheader("Portfolio Summary")
cols = st.columns(4)
cols[0].metric("Total Value", f"${total_value:,.2f}")
cols[1].metric("Total Cost", f"${total_cost:,.2f}")
cols[2].metric("Unrealized P&L", f"${day_pnl:,.2f}",
               f"{total_return:+.2f}%")
cols[3].metric("Positions", str(len(holdings)))

# ── Allocation Pie Chart ──────────────────────────────────────────────
st.divider()
st.subheader("Current Allocation")

labels = []
values = []
for h in holdings:
    labels.append(h["symbol"])
    values.append(h["quantity"] * prices.get(h["symbol"], h["avg_cost"]))

acol1, acol2 = st.columns(2)
with acol1:
    fig = pie_chart(labels, values, "Current Allocation")
    st.plotly_chart(fig, use_container_width=True)

# ── Holdings Table ────────────────────────────────────────────────────
with acol2:
    st.subheader("Holdings Detail")
    holdings_table(holdings, prices)

# ── Remove Holding ────────────────────────────────────────────────────
with st.expander("🗑️ Remove Holding"):
    remove_sym = st.selectbox("Select holding to remove",
                              [h["symbol"] for h in holdings], key="remove_sym")
    if st.button("Remove", type="secondary"):
        remove_holding(remove_sym)
        st.success(f"Removed {remove_sym}")
        st.rerun()

# ── Portfolio Optimization ────────────────────────────────────────────
st.divider()
st.subheader("Portfolio Optimization")

opt_method = st.selectbox("Optimization Method",
                          ["min_volatility", "max_sharpe", "efficient_risk"],
                          format_func=lambda x: {"min_volatility": "Minimum Volatility (Conservative)",
                                                  "max_sharpe": "Maximum Sharpe Ratio",
                                                  "efficient_risk": "Efficient Risk (15% target vol)"}.get(x, x))

if st.button("Run Optimization", type="primary"):
    with st.spinner("Fetching price history and optimizing..."):
        price_data = {}
        for h in holdings:
            sym = h["symbol"]
            try:
                if h["asset_type"] == "crypto":
                    from data.crypto_fetcher import fetch_crypto_data
                    df = fetch_crypto_data(sym, days=365)
                else:
                    df = fetch_stock_data(sym, period="1y")
                if df is not None and not df.empty:
                    price_data[sym] = df
            except Exception:
                continue

        if len(price_data) >= 2:
            returns = build_returns_from_prices(price_data)
            result = optimize_portfolio(returns, method=opt_method)

            if "error" in result:
                st.error(result["error"])
            else:
                st.success(f"Optimization complete (Sharpe: {result['sharpe_ratio']:.2f})")

                rcol1, rcol2 = st.columns(2)
                with rcol1:
                    opt_labels = list(result["weights"].keys())
                    opt_values = list(result["weights"].values())
                    fig = pie_chart(opt_labels, opt_values, "Optimal Allocation")
                    st.plotly_chart(fig, use_container_width=True)

                with rcol2:
                    st.metric("Expected Annual Return", f"{result['expected_annual_return']:.2%}")
                    st.metric("Annual Volatility", f"{result['annual_volatility']:.2%}")
                    st.metric("Sharpe Ratio", f"{result['sharpe_ratio']:.2f}")

                # Rebalance suggestions
                current_weights = {h["symbol"]: (h["quantity"] * prices.get(h["symbol"], 0)) / total_value
                                   for h in holdings}
                suggestions = get_rebalance_suggestions(current_weights, result["weights"], total_value)
                if suggestions:
                    st.subheader("Rebalance Suggestions")
                    st.dataframe(pd.DataFrame(suggestions), use_container_width=True, hide_index=True)
        else:
            st.warning("Need at least 2 assets with data for optimization.")

# ── Transaction History ───────────────────────────────────────────────
st.divider()
st.subheader("Transaction History")
transactions = get_transactions(50)
transaction_table(transactions)
