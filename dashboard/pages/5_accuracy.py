"""Signal Accuracy Analytics — track how well AI signals have performed."""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from analysis.accuracy_tracker import get_accuracy_stats, compute_adaptive_weights
from db.models import get_latest_signals
from i18n import t

st.title("📈 Signal Accuracy Analytics")
st.caption(
    "Tracks how historical BUY/SELL/HOLD signals performed over the following 5 trading days. "
    "Signals are evaluated automatically each scheduler scan."
)

# ── Trigger on-demand accuracy check ─────────────────────────────────
if st.button("🔄 Run Accuracy Check Now", type="primary"):
    with st.spinner("Evaluating past signals..."):
        try:
            from analysis.accuracy_tracker import run_accuracy_check
            result = run_accuracy_check()
            if result["checked"] > 0:
                st.success(
                    f"Evaluated {result['checked']} signals · "
                    f"Accuracy: {result['accuracy']*100:.1f}%"
                )
            else:
                st.info("No new signals ready to evaluate (signals need ≥5 trading days).")
        except Exception as e:
            st.error(f"Accuracy check failed: {e}")

st.divider()

# ── Load stats ────────────────────────────────────────────────────────
try:
    stats = get_accuracy_stats()
except Exception as e:
    st.error(f"Could not load accuracy stats: {e}")
    st.stop()

total = stats.get("total_evaluated", 0)

if total == 0:
    st.info(
        "No evaluated signals yet. Signals need at least 5 trading days before they can be "
        "evaluated. Run the scheduler or click 'Run Accuracy Check Now' above."
    )
    st.stop()

# ── Headline metrics ──────────────────────────────────────────────────
st.subheader("Overall Performance")

m1, m2, m3, m4 = st.columns(4)
overall_acc = stats.get("overall_accuracy", 0)
correct = stats.get("correct", 0)

acc_color = "#27ae60" if overall_acc >= 0.6 else "#e67e22" if overall_acc >= 0.5 else "#c0392b"
with m1:
    st.markdown(
        f"""<div style="text-align:center;padding:12px;border-radius:8px;
        border:2px solid {acc_color};">
        <div style="font-size:.85em;color:#888;">Overall Accuracy</div>
        <div style="font-size:2.2em;font-weight:bold;color:{acc_color};">
        {overall_acc*100:.1f}%</div>
        </div>""",
        unsafe_allow_html=True,
    )
with m2:
    st.metric("Signals Evaluated", total)
with m3:
    st.metric("Correct", correct)
with m4:
    st.metric("Incorrect", total - correct)

st.divider()

# ── Accuracy by direction ─────────────────────────────────────────────
st.subheader("Accuracy by Signal Direction")

by_dir = stats.get("by_direction", {})
dir_rows = []
for direction in ("BUY", "SELL", "HOLD"):
    d = by_dir.get(direction, {})
    if d.get("total", 0) > 0:
        dir_rows.append({
            "Direction": direction,
            "Total":     d["total"],
            "Correct":   d["correct"],
            "Accuracy":  f"{d['accuracy']*100:.1f}%",
            "Avg 5d Return": f"{d['avg_return_5d']*100:+.2f}%",
        })

if dir_rows:
    df_dir = pd.DataFrame(dir_rows)

    # Color-code accuracy
    def _color_accuracy(val):
        try:
            pct = float(val.replace("%", ""))
        except (ValueError, AttributeError):
            return ""
        if pct >= 60:
            return "color: #27ae60; font-weight: bold"
        elif pct >= 50:
            return "color: #e67e22"
        return "color: #c0392b"

    def _color_return(val):
        try:
            pct = float(val.replace("%", ""))
        except (ValueError, AttributeError):
            return ""
        return "color: #27ae60" if pct > 0 else "color: #c0392b" if pct < 0 else ""

    st.dataframe(
        df_dir.style
            .map(_color_accuracy, subset=["Accuracy"])
            .map(_color_return,   subset=["Avg 5d Return"]),
        use_container_width=True,
        hide_index=True,
    )

    # Bar chart of accuracy by direction
    try:
        import plotly.graph_objects as go

        dirs   = [r["Direction"] for r in dir_rows]
        accs   = [float(r["Accuracy"].replace("%", "")) for r in dir_rows]
        colors = ["#27ae60" if a >= 60 else "#e67e22" if a >= 50 else "#c0392b" for a in accs]

        fig = go.Figure(go.Bar(
            x=dirs, y=accs,
            marker_color=colors,
            text=[f"{a:.1f}%" for a in accs],
            textposition="outside",
        ))
        fig.update_layout(
            yaxis_title="Accuracy (%)",
            yaxis_range=[0, 105],
            showlegend=False,
            height=300,
            margin=dict(t=20, b=20),
        )
        fig.add_hline(y=50, line_dash="dash", line_color="#7f8c8d",
                      annotation_text="50% baseline")
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass

st.divider()

# ── Factor performance ────────────────────────────────────────────────
st.subheader("Factor Scores: Correct vs Incorrect Signals")

by_factor = stats.get("by_factor", {})
if by_factor:
    factor_rows = []
    for label in ("correct", "incorrect"):
        fd = by_factor.get(label, {})
        if fd:
            factor_rows.append({
                "Outcome":      label.capitalize(),
                "Avg Technical": f"{fd.get('avg_technical', 0):+.4f}",
                "Avg Sentiment": f"{fd.get('avg_sentiment', 0):+.4f}",
                "Avg ML":        f"{fd.get('avg_ml', 0):+.4f}",
            })
    if factor_rows:
        st.dataframe(pd.DataFrame(factor_rows), use_container_width=True, hide_index=True)
        st.caption(
            "Correct signals tend to have higher absolute factor scores with more alignment. "
            "Divergent factors (e.g. bullish technical + bearish ML) lead to more errors."
        )

st.divider()

# ── Adaptive weights in use ───────────────────────────────────────────
st.subheader("Current Adaptive Factor Weights")

try:
    weights = compute_adaptive_weights()
    w_col1, w_col2, w_col3, w_col4 = st.columns(4)

    from config import SIGNAL_WEIGHTS
    for col, (factor, label) in zip(
        [w_col1, w_col2, w_col3, w_col4],
        [("technical", "Technical"), ("sentiment", "Sentiment"),
         ("ml", "ML"), ("macro", "Macro")]
    ):
        with col:
            w_val   = weights.get(factor, 0)
            w_base  = SIGNAL_WEIGHTS.get(factor, 0)
            delta   = w_val - w_base
            d_color = "#27ae60" if delta > 0.005 else "#c0392b" if delta < -0.005 else "#888"
            st.markdown(
                f"""<div style="text-align:center;padding:10px;border-radius:6px;
                border:1px solid #ddd;">
                <div style="font-size:.8em;color:#888;">{label}</div>
                <div style="font-size:1.6em;font-weight:bold;">{w_val*100:.1f}%</div>
                <div style="font-size:.8em;color:{d_color};">
                {f'{delta*100:+.1f}% vs config' if abs(delta) > 0.001 else 'at config'}</div>
                </div>""",
                unsafe_allow_html=True,
            )
    st.caption(
        "Weights are blended 50/50 between historical performance (point-biserial correlation) "
        "and config priors. Macro weight is always held at the config value."
    )
except Exception as e:
    st.warning(f"Could not compute adaptive weights: {e}")

st.divider()

# ── Recent signal outcomes table ──────────────────────────────────────
st.subheader("Recent Signal Outcomes")

recent = get_latest_signals(100)
evaluated = [s for s in recent if s.get("outcome_correct") is not None]

if evaluated:
    outcome_rows = []
    for s in evaluated[:50]:
        ret_5d = s.get("outcome_return_5d")
        outcome_rows.append({
            "Date":      s["created_at"][:10] if s.get("created_at") else "—",
            "Symbol":    s["symbol"],
            "Direction": s["direction"],
            "Strength":  f"{s.get('strength', 0):+.3f}",
            "Confidence":f"{s.get('confidence', 0)*100:.0f}%",
            "5d Return": f"{ret_5d*100:+.2f}%" if ret_5d is not None else "—",
            "Correct":   "Yes" if s["outcome_correct"] == 1 else "No",
        })

    df_out = pd.DataFrame(outcome_rows)

    def _style_correct(val):
        if val == "Yes":
            return "color: #27ae60; font-weight: bold"
        elif val == "No":
            return "color: #c0392b; font-weight: bold"
        return ""

    def _style_direction(val):
        if val == "BUY":
            return "color: #27ae60; font-weight: bold"
        elif val == "SELL":
            return "color: #c0392b; font-weight: bold"
        return ""

    def _style_return(val):
        try:
            pct = float(val.replace("%", ""))
        except (ValueError, AttributeError):
            return ""
        return "color: #27ae60" if pct > 0 else "color: #c0392b" if pct < 0 else ""

    st.dataframe(
        df_out.style
            .map(_style_correct,   subset=["Correct"])
            .map(_style_direction, subset=["Direction"])
            .map(_style_return,    subset=["5d Return"]),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No evaluated signals in the last 100 signals.")

st.divider()

# ── Symbol-level breakdown ─────────────────────────────────────────────
st.subheader("Accuracy by Symbol")

all_signals = get_latest_signals(500)
evaluated_all = [s for s in all_signals if s.get("outcome_correct") is not None]

if evaluated_all:
    from collections import defaultdict
    sym_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "returns": []})
    for s in evaluated_all:
        sym = s["symbol"]
        sym_stats[sym]["total"] += 1
        sym_stats[sym]["correct"] += s.get("outcome_correct", 0) or 0
        ret = s.get("outcome_return_5d")
        if ret is not None:
            sym_stats[sym]["returns"].append(ret)

    sym_rows = []
    for sym, d in sym_stats.items():
        acc = d["correct"] / d["total"] if d["total"] > 0 else 0
        avg_ret = sum(d["returns"]) / len(d["returns"]) if d["returns"] else 0
        sym_rows.append({
            "Symbol":        sym,
            "Signals":       d["total"],
            "Correct":       d["correct"],
            "Accuracy":      f"{acc*100:.1f}%",
            "Avg 5d Return": f"{avg_ret*100:+.2f}%",
        })

    sym_rows.sort(key=lambda x: float(x["Accuracy"].replace("%", "")), reverse=True)
    st.dataframe(
        pd.DataFrame(sym_rows).style
            .map(_color_accuracy, subset=["Accuracy"])
            .map(_color_return,   subset=["Avg 5d Return"]),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No evaluated signals available for symbol breakdown.")
