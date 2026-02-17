"""Data table display components."""

import streamlit as st
import pandas as pd


def holdings_table(holdings: list[dict], prices: dict[str, float] | None = None):
    """Display portfolio holdings with current values."""
    if not holdings:
        st.caption("No holdings in portfolio.")
        return

    df = pd.DataFrame(holdings)
    if prices:
        df["current_price"] = df["symbol"].map(lambda s: prices.get(s, 0))
        df["market_value"] = df["quantity"] * df["current_price"]
        df["unrealized_pnl"] = (df["current_price"] - df["avg_cost"]) * df["quantity"]
        df["pnl_pct"] = ((df["current_price"] / df["avg_cost"]) - 1) * 100
    st.dataframe(df, use_container_width=True, hide_index=True)


def transaction_table(transactions: list[dict]):
    """Display transaction history."""
    if not transactions:
        st.caption("No transactions recorded.")
        return
    df = pd.DataFrame(transactions)
    st.dataframe(df, use_container_width=True, hide_index=True)


def news_table(articles: list[dict]):
    """Display news articles."""
    if not articles:
        st.caption("No news available.")
        return
    for art in articles[:10]:
        title = art.get("title", "Untitled")
        source = art.get("source", "")
        published = art.get("published_at", "")[:10]
        url = art.get("url", "")
        st.markdown(f"**{title}**  \n{source} | {published}")
        if url:
            st.caption(url)
        st.divider()
