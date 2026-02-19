"""Paper Trading — virtual portfolio that auto-executes AI signals."""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from i18n import t

zh = st.session_state.get("lang", "zh") == "zh"

st.title("🧪 " + ("模擬交易（紙上交易）" if zh else "Paper Trading"))
st.caption(
    "用虛擬資金測試策略，觀察 AI 訊號的實際執行效果，無需承擔真實虧損。"
    if zh else
    "Test strategies with virtual money — see how AI signals perform in real time, risk-free."
)

# ── Load PaperTrader ──────────────────────────────────────────────────
from strategy.paper_trader import PaperTrader
from db.models import get_paper_trades, reset_paper_portfolio, get_paper_positions

initial_cap = float(st.session_state.get("paper_capital", 100_000))
pos_pct     = float(st.session_state.get("paper_pos_pct", 0.10))
trader = PaperTrader(initial_capital=initial_cap, position_size_pct=pos_pct)

# ════════════════════════════════════════════════════════════════════════
# Sidebar controls
# ════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ " + ("模擬設定" if zh else "Paper Settings"))
    new_cap = st.number_input(
        "虛擬資金 (元)" if zh else "Virtual Capital ($)",
        min_value=10_000, max_value=10_000_000,
        value=int(initial_cap), step=10_000,
    )
    new_pct = st.slider(
        "單筆倉位 %" if zh else "Position Size %",
        min_value=1, max_value=30, value=int(pos_pct * 100)
    )
    if st.button("套用設定" if zh else "Apply Settings"):
        st.session_state["paper_capital"] = float(new_cap)
        st.session_state["paper_pos_pct"] = new_pct / 100
        st.success("✅ " + ("已更新" if zh else "Settings applied"))
        st.rerun()

    st.divider()
    if st.button("🔄 " + ("重置投資組合" if zh else "Reset Portfolio"),
                 type="secondary", use_container_width=True):
        reset_paper_portfolio()
        st.success("✅ " + ("已重置" if zh else "Portfolio reset"))
        st.rerun()

# ════════════════════════════════════════════════════════════════════════
# Tab layout
# ════════════════════════════════════════════════════════════════════════
tab_labels = (
    ["📊 投資組合總覽", "📋 持倉明細", "📜 交易記錄", "▶️ 手動執行訊號"]
    if zh else
    ["📊 Portfolio Overview", "📋 Open Positions", "📜 Trade History", "▶️ Execute Signal"]
)
tabs = st.tabs(tab_labels)

# ── Tab 1: Portfolio Overview ─────────────────────────────────────────
with tabs[0]:
    summary = trader.get_portfolio_summary()

    col1, col2, col3, col4 = st.columns(4)
    ret_pct = summary["total_return"] * 100
    col1.metric(
        "虛擬總資產" if zh else "Total Value",
        f"${summary['total_value']:,.0f}",
        f"{ret_pct:+.2f}%",
        delta_color="normal",
    )
    col2.metric(
        "可用現金" if zh else "Cash",
        f"${summary['cash']:,.0f}",
    )
    col3.metric(
        "未實現損益" if zh else "Unrealized P&L",
        f"${summary['unrealized_pnl']:+,.0f}",
        delta_color="normal" if summary["unrealized_pnl"] >= 0 else "inverse",
    )
    col4.metric(
        "已實現損益" if zh else "Realized P&L",
        f"${summary['realized_pnl']:+,.0f}",
        delta_color="normal" if summary["realized_pnl"] >= 0 else "inverse",
    )

    st.divider()
    n = summary["n_positions"]
    st.info(
        f"目前持有 **{n}** 個虛擬倉位。初始資金：${initial_cap:,.0f}"
        if zh else
        f"Currently holding **{n}** virtual position(s). Initial capital: ${initial_cap:,.0f}"
    )

    # Near-stop alerts
    alerts = [p for p in summary["positions"]
              if p.get("dist_to_stop_pct") is not None and p["dist_to_stop_pct"] < 5]
    if alerts:
        for a in alerts:
            st.warning(
                f"⚠️ **{a['symbol']}** 距止損僅 {a['dist_to_stop_pct']:.1f}%！"
                if zh else
                f"⚠️ **{a['symbol']}** is only {a['dist_to_stop_pct']:.1f}% from stop-loss!"
            )

# ── Tab 2: Open Positions ─────────────────────────────────────────────
with tabs[1]:
    positions = summary["positions"]
    if not positions:
        st.info("目前沒有開倉。" if zh else "No open positions.")
    else:
        rows = []
        for p in positions:
            rows.append({
                ("標的" if zh else "Symbol"):     p["symbol"],
                ("進場價" if zh else "Entry"):    f"${p['entry_price']:.2f}",
                ("現價" if zh else "Current"):    f"${p['current_price']:.2f}",
                ("股數" if zh else "Qty"):         f"{p['quantity']:.2f}",
                ("未實現損益" if zh else "Unreal. P&L"): f"${p['unrealized_pnl']:+,.2f}",
                ("漲跌" if zh else "Change"):      f"{p['pct_change']:+.2f}%",
                ("止損價" if zh else "Stop"):      f"${p['stop_loss']:.2f}" if p.get("stop_loss") else "—",
                ("距止損" if zh else "Dist"):      f"{p['dist_to_stop_pct']:.1f}%" if p.get("dist_to_stop_pct") is not None else "—",
                ("開倉時間" if zh else "Opened"):  p.get("opened_at", "")[:10],
            })
        df = pd.DataFrame(rows)

        def _color_pnl(val):
            if isinstance(val, str) and val.startswith("$"):
                try:
                    num = float(val.replace("$", "").replace(",", "").replace("+", ""))
                    color = "#27ae60" if num > 0 else ("#e74c3c" if num < 0 else "")
                    return f"color: {color}"
                except ValueError:
                    pass
            return ""

        styled = df.style.applymap(
            _color_pnl,
            subset=[("未實現損益" if zh else "Unreal. P&L"),
                    ("漲跌" if zh else "Change")]
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Tab 3: Trade History ──────────────────────────────────────────────
with tabs[2]:
    trades = get_paper_trades(200)
    if not trades:
        st.info("尚無交易記錄。" if zh else "No trades yet.")
    else:
        rows = []
        for t in trades:
            rows.append({
                ("時間" if zh else "Time"):        t.get("executed_at", "")[:16],
                ("標的" if zh else "Symbol"):      t["symbol"],
                ("動作" if zh else "Action"):      t["action"],
                ("價格" if zh else "Price"):        f"${t['price']:.2f}",
                ("數量" if zh else "Qty"):          f"{t['quantity']:.2f}",
                ("損益" if zh else "P&L"):          f"${t['pnl']:+,.2f}",
                ("原因" if zh else "Reason"):       t.get("reason", ""),
            })
        df_t = pd.DataFrame(rows)
        st.dataframe(df_t, use_container_width=True, hide_index=True)

        # Summary stats
        closed = [t for t in trades if t["action"] in ("SELL", "STOP")]
        if closed:
            total_pnl = sum(t["pnl"] for t in closed)
            wins = sum(1 for t in closed if t["pnl"] > 0)
            st.divider()
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("總已實現損益" if zh else "Total Realized P&L",
                       f"${total_pnl:+,.2f}")
            sc2.metric("勝率" if zh else "Win Rate",
                       f"{wins/len(closed)*100:.1f}%" if closed else "—")
            sc3.metric("已平倉筆數" if zh else "Closed Trades", len(closed))

# ── Tab 4: Manual Signal Execution ───────────────────────────────────
with tabs[3]:
    st.subheader("手動模擬下單" if zh else "Manual Signal Execution")
    st.caption(
        "從最近 AI 訊號中選擇一個，手動送入模擬交易引擎。"
        if zh else
        "Pick a recent AI signal and execute it into the paper portfolio."
    )

    from db.models import get_latest_signals
    recent_sigs = [s for s in get_latest_signals(50)
                   if s.get("direction") in ("BUY", "SELL")]

    if not recent_sigs:
        st.info("沒有可執行的 BUY/SELL 訊號。" if zh else "No BUY/SELL signals available.")
    else:
        sig_options = {
            f"{s['symbol']} {s['direction']} "
            f"(強度{s['strength']:+.2f} 信心{s['confidence']*100:.0f}%) "
            f"@ {str(s.get('created_at',''))[:16]}": s
            for s in recent_sigs[:20]
        }
        chosen_label = st.selectbox(
            "選擇訊號" if zh else "Select signal", list(sig_options.keys())
        )
        chosen_sig = sig_options[chosen_label]

        price_input = st.number_input(
            "執行價格（可手動調整）" if zh else "Execution price (editable)",
            min_value=0.01, value=100.00, step=0.01, format="%.2f"
        )

        if st.button("▶️ " + ("執行模擬" if zh else "Execute Paper Trade"),
                     type="primary"):
            action = trader.process_signal(
                symbol=chosen_sig["symbol"],
                signal=chosen_sig,
                current_price=price_input,
            )
            if action:
                st.success(
                    f"✅ 已模擬 **{action}** {chosen_sig['symbol']} @ ${price_input:.2f}"
                    if zh else
                    f"✅ Paper **{action}** {chosen_sig['symbol']} @ ${price_input:.2f}"
                )
                st.rerun()
            else:
                st.warning(
                    "未執行 — 可能原因：已持有此標的（BUY）/ 未持有此標的（SELL）/ 現金不足"
                    if zh else
                    "Not executed — already holding this symbol (BUY) / not holding (SELL) / insufficient cash"
                )
