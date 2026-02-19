"""Help & Beginner's Guide — practical usage advice for new investors."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from i18n import t

# ── Detect language ───────────────────────────────────────────────────
_lang = st.session_state.get("lang", "zh")
_zh = _lang == "zh"

st.title("📖 " + t("help_guide"))

# ── Top disclaimer banner ─────────────────────────────────────────────
st.info(
    "⚠️ " + (
        "本系統訊號僅供學習與參考，不構成任何投資建議。投資有風險，決策前請審慎評估。"
        if _zh else
        "Signals are for educational/reference purposes only and do not constitute "
        "investment advice. All investments involve risk."
    ),
    icon="⚠️",
)

# ── Tabs ──────────────────────────────────────────────────────────────
tab_labels = (
    ["🚀 入門步驟", "📊 看懂訊號", "🔁 回測指引", "🛡️ 風險警示", "📅 每日流程", "❌ 常見誤區"]
    if _zh else
    ["🚀 Getting Started", "📊 Reading Signals", "🔁 Backtest Guide",
     "🛡️ Risk Warnings", "📅 Daily Workflow", "❌ Common Mistakes"]
)

t1, t2, t3, t4, t5, t6 = st.tabs(tab_labels)


# ════════════════════════════════════════════════════════════════════════
# Tab 1 — Getting Started
# ════════════════════════════════════════════════════════════════════════
with t1:
    if _zh:
        st.subheader("第一步：先觀察，不要急著交易")
        st.markdown("""
開啟系統後，建議**花 1–2 週只看不動**，培養對市場的感覺。

| 頁面 | 建議每日做什麼 |
|------|---------------|
| **市場總覽** | 看整體市場走向、Fear & Greed 指數 |
| **AI 訊號** | 觀察哪些標的出現訊號，先不操作 |
| **風控監控** | 了解回撤保護機制的運作方式 |
| **回測** | 測試你感興趣的標的歷史表現 |
""")

        with st.expander("💡 實例：第一天打開系統，我應該看什麼？"):
            st.markdown("""
**情境：** 小明第一次打開系統，想了解現在市場狀況。

**Step 1 → 打開「市場總覽」**
- Fear & Greed 指數顯示 **28（Extreme Fear）**
- Macro Regime：**NEUTRAL**
- 大盤近一週下跌約 3%

**小明的解讀：**
> 市場情緒偏恐慌，但整體總經還算中性。歷史上「極度恐懼」有時是逢低布局的機會，
> 但還不能直接進場——需要等 AI 訊號出現且各條件都滿足才行。

**Step 2 → 打開「AI 訊號」，只觀察，不操作**
- 看到 AAPL 顯示 HOLD、MSFT 顯示 BUY（但 Confidence 只有 52%）
- **這週不動**，因為信心度未達 65%。繼續觀察。
""")

        st.subheader("第二步：設定你的觀察清單")
        st.markdown("""
前往 **系統設定 → 自選清單**，加入你想追蹤的股票或加密貨幣。

**股票建議入門組合（舉例）：**
- 大型穩定股：AAPL、MSFT、GOOGL
- ETF（風險最低）：SPY、QQQ

**加密貨幣建議入門組合（舉例）：**
- BTC/USDT、ETH/USDT
- 加密貨幣波動極大，**建議佔總資金 ≤ 20%**
""")

        with st.expander("💡 實例：我有 20 萬元，應該怎麼分配標的？"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**保守型（穩健優先）**")
                st.markdown("""
| 標的 | 配置 | 金額 |
|------|------|------|
| SPY（S&P500 ETF）| 40% | 8 萬 |
| QQQ（科技 ETF）| 30% | 6 萬 |
| AAPL | 20% | 4 萬 |
| BTC/USDT | 10% | 2 萬 |
""")
            with col2:
                st.markdown("**積極型（接受較高波動）**")
                st.markdown("""
| 標的 | 配置 | 金額 |
|------|------|------|
| AAPL | 25% | 5 萬 |
| MSFT | 25% | 5 萬 |
| GOOGL | 20% | 4 萬 |
| BTC/USDT | 20% | 4 萬 |
| ETH/USDT | 10% | 2 萬 |
""")
            st.warning("以上僅為分配示例，不構成投資建議。")

        st.subheader("第三步：用回測建立信心再進場")
        st.markdown("""
**在投入真實資金前，先回測：**

1. 前往 **回測** 頁面
2. 選擇你感興趣的標的
3. 選 **Technical（技術）** 模式，跑完整歷史
4. 檢視 Max Drawdown（最大回撤）是否 < 20%
5. Sharpe Ratio > 1.0 表示風險調整後報酬不錯

確認歷史表現合理後，再考慮進場。
""")

    else:
        st.subheader("Step 1 — Watch First, Trade Later")
        st.markdown("""
After opening the system, spend **1–2 weeks observing without trading** to develop a feel for the market.

| Page | Daily Action |
|------|-------------|
| **Market Overview** | Check market sentiment & Fear/Greed index |
| **AI Signals** | Watch which symbols generate signals — don't act yet |
| **Risk Monitor** | Understand how drawdown protection works |
| **Backtest** | Test historical performance of symbols you're interested in |
""")

        with st.expander("💡 Example: What should I look at on Day 1?"):
            st.markdown("""
**Scenario:** Alice opens the system for the first time.

**Step 1 → Open "Market Overview"**
- Fear & Greed index shows **28 (Extreme Fear)**
- Macro Regime: **NEUTRAL**
- Market down ~3% over the past week

**Alice's interpretation:**
> The market is in panic mode, but macro conditions are still neutral.
> Historically, Extreme Fear can signal buying opportunities — but she can't enter yet.
> She needs to wait for a proper AI signal with Confidence ≥ 65%.

**Step 2 → Open "AI Signals" — observe only, no action**
- AAPL shows HOLD, MSFT shows BUY (but Confidence is only 52%)
- **No action this week** — Confidence hasn't hit 65%. Keep watching.
""")

        st.subheader("Step 2 — Set Up Your Watchlist")
        st.markdown("""
Go to **Settings → Watchlist** and add the stocks or crypto you want to track.

**Beginner stock suggestions:**
- Large-cap stable stocks: AAPL, MSFT, GOOGL
- ETFs (lowest risk): SPY, QQQ

**Beginner crypto suggestions:**
- BTC/USDT, ETH/USDT
- Crypto is highly volatile — **keep total crypto ≤ 20% of capital**
""")

        with st.expander("💡 Example: I have $20,000 — how should I allocate?"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Conservative (stability first)**")
                st.markdown("""
| Symbol | Allocation | Amount |
|--------|-----------|--------|
| SPY (S&P500 ETF) | 40% | $8,000 |
| QQQ (Tech ETF) | 30% | $6,000 |
| AAPL | 20% | $4,000 |
| BTC/USDT | 10% | $2,000 |
""")
            with col2:
                st.markdown("**Aggressive (higher volatility ok)**")
                st.markdown("""
| Symbol | Allocation | Amount |
|--------|-----------|--------|
| AAPL | 25% | $5,000 |
| MSFT | 25% | $5,000 |
| GOOGL | 20% | $4,000 |
| BTC/USDT | 20% | $4,000 |
| ETH/USDT | 10% | $2,000 |
""")
            st.warning("For illustration only. Not investment advice.")

        st.subheader("Step 3 — Backtest Before Committing Real Money")
        st.markdown("""
1. Go to the **Backtest** page
2. Select a symbol
3. Choose **Technical** mode and run the full history
4. Check if Max Drawdown < 20%
5. Sharpe Ratio > 1.0 = good risk-adjusted return

Only enter after confirming reasonable historical performance.
""")


# ════════════════════════════════════════════════════════════════════════
# Tab 2 — Reading Signals
# ════════════════════════════════════════════════════════════════════════
with t2:
    if _zh:
        st.subheader("每個訊號的三個核心數字")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Direction（方向）", "BUY / HOLD / SELL", help="系統建議的操作方向")
            st.caption("系統建議的操作方向，但需搭配 Strength 和 Confidence 一起判斷。")
        with col2:
            st.metric("Strength（強度）", "-1.0 ～ +1.0", help="訊號強度")
            st.caption("**> 0.4** 才值得認真考慮。強度越高，訊號越明確。")
        with col3:
            st.metric("Confidence（信心度）", "0% ～ 100%", help="各因子一致程度")
            st.caption("**≥ 65%** 才考慮進場。低信心表示各因子意見分歧。")

        st.divider()
        st.subheader("進場條件（建議三者同時滿足）")
        st.success("Direction = BUY　且　Strength ≥ 0.4　且　Confidence ≥ 65%")

        st.divider()
        st.subheader("實例：如何判斷一個訊號值不值得進場？")

        ex_col1, ex_col2 = st.columns(2)

        with ex_col1:
            st.markdown("#### ✅ 好訊號範例 — 可以考慮")
            st.markdown("**標的：AAPL**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Direction", "BUY", delta="強烈看多")
            m2.metric("Strength", "+0.62", delta="高於 0.4 門檻")
            m3.metric("Confidence", "74%", delta="高於 65% 門檻")
            st.markdown("""
| 因子 | 分數 | 方向 |
|------|------|------|
| Technical | +0.55 | ✅ 看多 |
| Sentiment | +0.48 | ✅ 看多 |
| ML Model  | +0.71 | ✅ 看多 |
| Macro     | +0.30 | ✅ 中性偏多 |
""")
            st.success("三個核心條件全部達標，各因子方向一致 → **可考慮進場**")

        with ex_col2:
            st.markdown("#### ❌ 壞訊號範例 — 應該跳過")
            st.markdown("**標的：TSLA**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Direction", "BUY", delta=None)
            m2.metric("Strength", "+0.31", delta="低於 0.4 門檻", delta_color="inverse")
            m3.metric("Confidence", "48%", delta="低於 65% 門檻", delta_color="inverse")
            st.markdown("""
| 因子 | 分數 | 方向 |
|------|------|------|
| Technical | +0.55 | ✅ 看多 |
| Sentiment | -0.20 | ❌ 看空 |
| ML Model  | +0.10 | ➖ 中性 |
| Macro     | -0.15 | ❌ 看空 |
""")
            st.error("雖然顯示 BUY，但 Strength 和 Confidence 都未達標，各因子意見分歧 → **應該跳過**")

        st.divider()
        st.subheader("各因子說明")
        st.markdown("""
| 因子 | 說明 | 適合新手理解的方式 |
|------|------|-----------------|
| **Technical Score** | RSI、MACD、布林帶等技術指標 | 看價格走勢的「溫度計」|
| **Sentiment Score** | 新聞與社群媒體情緒分析 | 市場上大家在說好還是說壞 |
| **ML Score** | XGBoost、LightGBM、LSTM 預測 | AI 根據歷史找到的規律 |
| **Macro Score** | 總經環境（利率、GDP、VIX）| 大環境是否有利投資 |
| **Sector Score** | 你的標的所在行業強弱 | 漲潮時哪個行業在領漲 |
| **Fear & Greed** | 市場恐懼貪婪指數 | 大家現在是恐慌還是過度樂觀 |
| **Options Signal** | 選擇權 Put/Call 比率 | 機構的「押注方向」參考 |
| **Pattern Score** | 雙底、整理突破等K線型態 | 歷史上類似的形態後來怎麼走 |
""")

    else:
        st.subheader("The Three Core Numbers in Every Signal")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Direction", "BUY / HOLD / SELL")
            st.caption("The system's recommended action. Must be read alongside Strength and Confidence.")
        with col2:
            st.metric("Strength", "-1.0 to +1.0")
            st.caption("**> 0.4** is worth acting on. Higher = clearer signal.")
        with col3:
            st.metric("Confidence", "0% to 100%")
            st.caption("**≥ 65%** before entering. Low confidence means factors disagree.")

        st.divider()
        st.subheader("Entry Conditions (all three should be met)")
        st.success("Direction = BUY   AND   Strength ≥ 0.4   AND   Confidence ≥ 65%")

        st.divider()
        st.subheader("Example: Is This Signal Worth Acting On?")

        ex_col1, ex_col2 = st.columns(2)

        with ex_col1:
            st.markdown("#### ✅ Good Signal — Consider Entering")
            st.markdown("**Symbol: AAPL**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Direction", "BUY", delta="Strong bullish")
            m2.metric("Strength", "+0.62", delta="Above 0.4 threshold")
            m3.metric("Confidence", "74%", delta="Above 65% threshold")
            st.markdown("""
| Factor | Score | Direction |
|--------|-------|-----------|
| Technical | +0.55 | ✅ Bullish |
| Sentiment | +0.48 | ✅ Bullish |
| ML Model  | +0.71 | ✅ Bullish |
| Macro     | +0.30 | ✅ Neutral-bullish |
""")
            st.success("All three core conditions met, factors aligned → **Consider entering**")

        with ex_col2:
            st.markdown("#### ❌ Weak Signal — Skip It")
            st.markdown("**Symbol: TSLA**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Direction", "BUY")
            m2.metric("Strength", "+0.31", delta="Below 0.4 threshold", delta_color="inverse")
            m3.metric("Confidence", "48%", delta="Below 65% threshold", delta_color="inverse")
            st.markdown("""
| Factor | Score | Direction |
|--------|-------|-----------|
| Technical | +0.55 | ✅ Bullish |
| Sentiment | -0.20 | ❌ Bearish |
| ML Model  | +0.10 | ➖ Neutral |
| Macro     | -0.15 | ❌ Bearish |
""")
            st.error("Shows BUY but Strength and Confidence both below threshold, factors disagree → **Skip**")

        st.divider()
        st.subheader("Factor Explanations")
        st.markdown("""
| Factor | Description | Beginner Interpretation |
|--------|-------------|------------------------|
| **Technical Score** | RSI, MACD, Bollinger Bands | Price trend thermometer |
| **Sentiment Score** | News & social media NLP | Is the crowd optimistic or pessimistic? |
| **ML Score** | XGBoost, LightGBM, LSTM | AI patterns from historical data |
| **Macro Score** | Interest rates, GDP, VIX | Is the macro environment favorable? |
| **Sector Score** | Sector momentum vs market | Is your sector leading or lagging? |
| **Fear & Greed** | Market sentiment index | Is the market panicking or too greedy? |
| **Options Signal** | Put/Call ratio & IV skew | What are institutions betting on? |
| **Pattern Score** | Double bottom, breakout, etc. | Historical chart pattern signals |
""")


# ════════════════════════════════════════════════════════════════════════
# Tab 3 — Backtest Guide
# ════════════════════════════════════════════════════════════════════════
with t3:
    if _zh:
        st.subheader("如何看懂回測結果")
        st.markdown("""
| 指標 | 說明 | 合格標準（入門參考）|
|------|------|---------------------|
| **Total Return** | 回測期間總報酬率 | 正值即可 |
| **Annual Return** | 年化報酬率 | > 10% 較佳 |
| **Sharpe Ratio** | 風險調整後報酬 | **≥ 1.0** |
| **Sortino Ratio** | 只算下行風險的夏普 | **≥ 1.0** |
| **Max Drawdown** | 最大回撤（最痛的跌幅）| **< 20%** |
| **Calmar Ratio** | 年化報酬 / 最大回撤 | > 0.5 較佳 |
| **Win Rate** | 獲利交易比例 | > 50% |
| **Profit Factor** | 總獲利 / 總虧損 | **> 1.5** |
""")

        st.divider()
        st.subheader("實例：好回測 vs 壞回測，怎麼分辨？")

        bt_col1, bt_col2 = st.columns(2)

        with bt_col1:
            st.markdown("#### ✅ 好的回測結果")
            st.markdown("**標的：AAPL（3年回測）**")
            c1, c2 = st.columns(2)
            c1.metric("Total Return", "+58%", delta="正報酬")
            c2.metric("Annual Return", "+17%", delta="高於 10% 基準")
            c1.metric("Sharpe Ratio", "1.42", delta="高於 1.0")
            c2.metric("Max Drawdown", "-14%", delta="控制在 20% 內")
            c1.metric("Win Rate", "61%", delta="超過 50%")
            c2.metric("Profit Factor", "1.9", delta="高於 1.5")
            st.success("各項指標均達標 → 這個策略值得信賴")

        with bt_col2:
            st.markdown("#### ❌ 看起來很好但其實很危險")
            st.markdown("**標的：某加密貨幣（3年回測）**")
            c1, c2 = st.columns(2)
            c1.metric("Total Return", "+210%", delta="看起來很高")
            c2.metric("Annual Return", "+45%", delta="看起來很好")
            c1.metric("Sharpe Ratio", "0.52", delta="低於 1.0", delta_color="inverse")
            c2.metric("Max Drawdown", "-68%", delta="遠超 20%！", delta_color="inverse")
            c1.metric("Win Rate", "38%", delta="低於 50%", delta_color="inverse")
            c2.metric("Profit Factor", "1.1", delta="接近盈虧平衡", delta_color="inverse")
            st.error("報酬率雖高，但最大回撤高達 68%，代表資金曾縮水超過一半 → **不適合新手**")

        st.caption("💡 重點：**不要只看報酬率，最大回撤才是衡量你能否撐過去的關鍵。**")

        st.divider()
        st.subheader("Walk-Forward 驗證（進階）")
        st.markdown("""
系統支援 **Walk-Forward 驗證**，比單純回測更能防止「過擬合」：

- 把歷史資料切成多個滾動窗口
- 每個窗口都測試策略在「未見過的資料」上的表現
- **OOS Sharpe 穩定** 表示策略有真實的邏輯，不只是湊合歷史數據
""")
        with st.expander("💡 實例：Walk-Forward 結果怎麼看？"):
            st.markdown("""
假設 Walk-Forward 跑了 5 個 OOS 窗口，結果如下：

| Fold | OOS 期間 | Sharpe | 報酬率 |
|------|---------|--------|--------|
| 1 | 2022 Q1 | 1.21 | +8.3% |
| 2 | 2022 Q2 | 0.88 | +4.1% |
| 3 | 2022 Q3 | 1.45 | +11.2% |
| 4 | 2022 Q4 | 1.03 | +6.8% |
| 5 | 2023 Q1 | 1.18 | +9.0% |

✅ **5 個窗口都是正報酬**（oos_positive_folds = 5/5 = 100%）
✅ Sharpe 穩定在 0.88–1.45，沒有忽高忽低
→ 這個策略在不同時期都能獲利，具有真實的邏輯

若某個 Fold 的 Sharpe 是 -2.0，代表那段時間策略完全失效，需要小心。
""")

        st.divider()
        st.subheader("Monte Carlo 模擬（進階）")
        st.markdown("""
系統支援 **Monte Carlo 蒙特卡洛模擬**，隨機重排交易順序 1000 次，估算：

- `prob_positive`：策略獲利的機率
- `max_drawdown p95`：最壞情況下的回撤
- 若 `p5 total_return` 仍為正值，表示策略在惡劣情況下也有韌性
""")
        with st.expander("💡 實例：Monte Carlo 結果怎麼看？"):
            st.markdown("""
模擬 1000 次的結果：

| 指標 | 最壞 5% | 中位數 | 最好 5% |
|------|--------|--------|--------|
| Total Return | -3.2% | +18.5% | +42.1% |
| Max Drawdown | 28.4% | 14.2% | 6.1% |
| Sharpe Ratio | 0.31 | 1.15 | 2.08 |

**解讀：**
- `p5 total_return = -3.2%`：最壞情況下虧損 3.2%，尚在可接受範圍
- `p95 max_drawdown = 28.4%`：即使運氣最差，最大回撤不超過 28%
- `prob_positive = 0.87`：87% 的模擬情境下，策略最終獲利

→ 這是相對穩健的策略結果
""")

    else:
        st.subheader("How to Read Backtest Results")
        st.markdown("""
| Metric | Description | Benchmark (beginner guide) |
|--------|-------------|---------------------------|
| **Total Return** | Overall return during backtest | Positive |
| **Annual Return** | Annualised return | > 10% preferred |
| **Sharpe Ratio** | Risk-adjusted return | **≥ 1.0** |
| **Sortino Ratio** | Sharpe using only downside risk | **≥ 1.0** |
| **Max Drawdown** | Worst peak-to-trough decline | **< 20%** |
| **Calmar Ratio** | Annual return / Max drawdown | > 0.5 preferred |
| **Win Rate** | Fraction of profitable trades | > 50% |
| **Profit Factor** | Gross profit / Gross loss | **> 1.5** |
""")

        st.divider()
        st.subheader("Example: Good Backtest vs Dangerous Backtest")

        bt_col1, bt_col2 = st.columns(2)

        with bt_col1:
            st.markdown("#### ✅ Good Backtest Result")
            st.markdown("**Symbol: AAPL (3-year backtest)**")
            c1, c2 = st.columns(2)
            c1.metric("Total Return", "+58%", delta="Positive")
            c2.metric("Annual Return", "+17%", delta="Above 10% target")
            c1.metric("Sharpe Ratio", "1.42", delta="Above 1.0")
            c2.metric("Max Drawdown", "-14%", delta="Within 20% limit")
            c1.metric("Win Rate", "61%", delta="Above 50%")
            c2.metric("Profit Factor", "1.9", delta="Above 1.5")
            st.success("All metrics pass → Strategy is trustworthy")

        with bt_col2:
            st.markdown("#### ❌ Looks Good But Actually Risky")
            st.markdown("**Symbol: A crypto asset (3-year backtest)**")
            c1, c2 = st.columns(2)
            c1.metric("Total Return", "+210%", delta="Looks great")
            c2.metric("Annual Return", "+45%", delta="Looks great")
            c1.metric("Sharpe Ratio", "0.52", delta="Below 1.0", delta_color="inverse")
            c2.metric("Max Drawdown", "-68%", delta="Way over 20%!", delta_color="inverse")
            c1.metric("Win Rate", "38%", delta="Below 50%", delta_color="inverse")
            c2.metric("Profit Factor", "1.1", delta="Near breakeven", delta_color="inverse")
            st.error("High return, but max drawdown of 68% means portfolio halved at worst → **Not suitable for beginners**")

        st.caption("💡 Key insight: **Never judge a strategy by returns alone. Max Drawdown tells you if you could survive the worst stretch.**")

        st.divider()
        st.subheader("Walk-Forward Validation (Advanced)")
        st.markdown("""
The system supports **Walk-Forward Validation** to prevent overfitting:

- Splits historical data into rolling windows
- Tests strategy performance on each unseen OOS period
- **Stable OOS Sharpe** = real logic, not just curve-fitted history
""")
        with st.expander("💡 Example: How to read Walk-Forward results?"):
            st.markdown("""
Suppose Walk-Forward ran 5 OOS windows:

| Fold | OOS Period | Sharpe | Return |
|------|-----------|--------|--------|
| 1 | 2022 Q1 | 1.21 | +8.3% |
| 2 | 2022 Q2 | 0.88 | +4.1% |
| 3 | 2022 Q3 | 1.45 | +11.2% |
| 4 | 2022 Q4 | 1.03 | +6.8% |
| 5 | 2023 Q1 | 1.18 | +9.0% |

✅ **All 5 windows profitable** (oos_positive_folds = 5/5 = 100%)
✅ Sharpe stable at 0.88–1.45 — no wild swings
→ Strategy performs consistently across different market periods

If one fold shows Sharpe = -2.0, the strategy completely broke down during that period — be cautious.
""")

        st.divider()
        st.subheader("Monte Carlo Simulation (Advanced)")
        st.markdown("""
The system shuffles trade order 1,000 times to estimate:
- `prob_positive` — probability the strategy stays profitable
- `max_drawdown p95` — worst-case drawdown scenario
""")
        with st.expander("💡 Example: How to read Monte Carlo results?"):
            st.markdown("""
After 1,000 simulations:

| Metric | Worst 5% | Median | Best 5% |
|--------|---------|--------|---------|
| Total Return | -3.2% | +18.5% | +42.1% |
| Max Drawdown | 28.4% | 14.2% | 6.1% |
| Sharpe Ratio | 0.31 | 1.15 | 2.08 |

**Interpretation:**
- `p5 total_return = -3.2%` — worst case is a small loss, acceptable
- `p95 max_drawdown = 28.4%` — even in bad luck, max drawdown stays under 30%
- `prob_positive = 0.87` — 87% of simulations ended profitably

→ This is a relatively robust strategy
""")


# ════════════════════════════════════════════════════════════════════════
# Tab 4 — Risk Warnings
# ════════════════════════════════════════════════════════════════════════
with t4:
    if _zh:
        st.subheader("系統內建警示：出現時請停止進場")

        st.error("**earnings_warning 出現** — 財報公布前後，不確定性極高，避免進場")
        st.error("**breadth_regime = POOR** — 大盤大多數股票走弱，不適合做多")
        st.error("**macro_regime = BEAR** — 總經環境轉熊，大幅降低倉位或觀望")
        st.warning("**risk_level = HIGH** — 訊號各因子意見分歧，可信度低，建議跳過")
        st.warning("**Drawdown Halt 觸發（> 12% 回撤）** — 系統自動停止新進場，請遵守")

        st.divider()
        st.subheader("實例：進場前如何計算倉位與止損？")

        with st.expander("💡 實例：我有 100,000 元，AAPL 出現 BUY 訊號，怎麼操作？"):
            st.markdown("""
**已知條件：**
- 總資金：100,000 元
- 標的：AAPL，目前股價 **$180**
- 系統訊號：BUY，Strength=0.62，Confidence=74%
- ATR（平均真實波幅）：約 **$4.5**（系統內部計算）
- 止損設定：進場價 - ATR × 2 倍
""")

            calc_col1, calc_col2 = st.columns(2)
            with calc_col1:
                st.markdown("**計算過程：**")
                st.markdown("""
| 項目 | 計算 | 結果 |
|------|------|------|
| 單筆倉位（10%）| 100,000 × 10% | **$10,000** |
| 可買股數 | 10,000 ÷ 180 | **≈ 55 股** |
| 實際花費 | 55 × 180 | **$9,900** |
| 止損價 | 180 - (4.5 × 2) | **$171** |
| 最大虧損 | (180 - 171) × 55 | **$495** |
| 佔總資金 | 495 ÷ 100,000 | **0.5%** |
""")
            with calc_col2:
                st.markdown("**結論：**")
                st.success("""
✅ 單筆動用 $9,900（9.9%），符合 ≤ 10% 原則
✅ 止損設在 $171，最壞虧損 $495（0.5% 總資金）
✅ 風險極低，即使止損觸發也不傷筋動骨

**進場指令：**
以市價買入 55 股 AAPL
同時設定 Stop-Loss @ $171
""")

        st.divider()
        st.subheader("資金管理原則")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
**每筆進場：**
- 單筆佔總資金 **≤ 10%**
- 設好止損後才進場
- 不要因為「感覺很確定」就加大倉位

**股票 vs 加密貨幣：**
- 加密貨幣波動是股票的 3–5 倍
- 建議加密貨幣總佔比 **≤ 20%**
""")
        with c2:
            st.markdown("""
**停損紀律：**
- 系統預設 ATR 倍數止損 + 移動止損
- 不要關掉止損「等反彈」
- 每筆最大虧損接受 **≤ 5% 總資金**

**心態：**
- 系統是輔助工具，不是保證獲利機器
- 連續虧損 3 筆後，暫停 1 週再看
""")

    else:
        st.subheader("Built-in System Warnings — Stop Entering When These Appear")

        st.error("**earnings_warning** — High uncertainty around earnings dates. Avoid entering.")
        st.error("**breadth_regime = POOR** — Most stocks in the market are weakening. Avoid longs.")
        st.error("**macro_regime = BEAR** — Macro environment has turned bearish. Reduce exposure or wait.")
        st.warning("**risk_level = HIGH** — Factors disagree. Low reliability. Skip this signal.")
        st.warning("**Drawdown Halt triggered (> 12%)** — System stops new entries automatically. Respect it.")

        st.divider()
        st.subheader("Example: How to Size a Position and Set a Stop-Loss?")

        with st.expander("💡 Example: I have $100,000 and AAPL shows a BUY signal. What do I do?"):
            st.markdown("""
**Given:**
- Total capital: $100,000
- Symbol: AAPL, current price **$180**
- Signal: BUY, Strength=0.62, Confidence=74%
- ATR (Average True Range): ~**$4.5** (calculated internally)
- Stop-loss rule: entry price − ATR × 2
""")
            calc_col1, calc_col2 = st.columns(2)
            with calc_col1:
                st.markdown("**Calculation:**")
                st.markdown("""
| Item | Calculation | Result |
|------|-------------|--------|
| Position size (10%) | $100,000 × 10% | **$10,000** |
| Shares to buy | $10,000 ÷ $180 | **≈ 55 shares** |
| Actual cost | 55 × $180 | **$9,900** |
| Stop-loss price | $180 − ($4.5 × 2) | **$171** |
| Max loss | ($180 − $171) × 55 | **$495** |
| % of capital | $495 ÷ $100,000 | **0.5%** |
""")
            with calc_col2:
                st.markdown("**Conclusion:**")
                st.success("""
✅ Using $9,900 (9.9%) — within the ≤ 10% rule
✅ Stop-loss at $171, max loss $495 (0.5% of capital)
✅ Very low risk — a stop-out won't hurt significantly

**Trade instruction:**
Buy 55 shares of AAPL at market price
Immediately set Stop-Loss @ $171
""")

        st.divider()
        st.subheader("Position Sizing Principles")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
**Per Trade:**
- Single position ≤ **10% of capital**
- Always set a stop-loss before entering
- Don't size up just because you "feel sure"

**Stocks vs Crypto:**
- Crypto is 3–5× more volatile than stocks
- Keep total crypto allocation ≤ **20% of capital**
""")
        with c2:
            st.markdown("""
**Stop-Loss Discipline:**
- System uses ATR-based + trailing stops by default
- Don't remove stops hoping for a recovery
- Maximum acceptable loss per trade: **≤ 5% of capital**

**Mindset:**
- This system is a decision-support tool, not a profit guarantee
- After 3 consecutive losses, take a 1-week break
""")


# ════════════════════════════════════════════════════════════════════════
# Tab 5 — Daily Workflow
# ════════════════════════════════════════════════════════════════════════
with t5:
    if _zh:
        st.subheader("每日 5 分鐘操作流程")

        st.markdown("### 開盤前（5 分鐘）")
        st.markdown("""
```
1. 市場總覽  →  確認 Fear & Greed 指數 + Macro Regime
2. AI 訊號   →  有無新的 BUY 訊號（需同時：Strength ≥ 0.4 + Confidence ≥ 65%）
3. 風控監控  →  確認自己的回撤仍在安全範圍（< 8%）
```
""")

        st.markdown("### 有訊號時的決策流程")
        st.markdown("""
```
訊號出現
   ↓
有 earnings_warning？ → 是 → 跳過
   ↓ 否
breadth_regime = POOR？ → 是 → 跳過
   ↓ 否
Strength ≥ 0.4 且 Confidence ≥ 65%？ → 否 → 跳過
   ↓ 是
回測此標的歷史 Sharpe > 1.0？ → 否 → 謹慎考慮
   ↓ 是
倉位 ≤ 10%，設好止損 → 進場
```
""")

        st.divider()
        st.subheader("實例：完整的一天操作紀錄")
        with st.expander("💡 實例：小明某個交易日的完整決策過程"):
            st.markdown("""
**早上 9:00（開盤前）**

**Step 1：市場總覽**
- Fear & Greed = **35（Fear）** — 市場略偏恐慌
- Macro Regime = **NEUTRAL** — 總經沒有明顯利空
- Market Breadth = **HEALTHY** — 大盤多數股票仍在均線以上

**Step 2：AI 訊號頁面**

看到兩個訊號：

| 標的 | Direction | Strength | Confidence | Risk Level |
|------|-----------|----------|-----------|-----------|
| MSFT | BUY | +0.55 | 71% | MEDIUM |
| NVDA | BUY | +0.38 | 49% | HIGH |

**Step 3：逐一過濾**

**MSFT：**
- earnings_warning？❌ 沒有
- breadth_regime = POOR？❌ 不是（HEALTHY）
- Strength ≥ 0.4？✅（0.55）
- Confidence ≥ 65%？✅（71%）
- → **通過篩選，可考慮進場**

**NVDA：**
- Strength ≥ 0.4？❌（0.38 < 0.4）
- Confidence ≥ 65%？❌（49% < 65%）
- → **直接跳過**

**Step 4：MSFT 回測確認**
- 跑回測：Sharpe = 1.28，Max Drawdown = -13%
- ✅ 兩項均達標

**Step 5：計算倉位**
- 總資金：100,000 元
- MSFT 股價：$380
- 進場金額：100,000 × 10% = $10,000
- 買入股數：10,000 ÷ 380 ≈ 26 股
- ATR ≈ $7.2，止損：380 - (7.2 × 2) = **$365.6**
- 最大虧損：(380 - 365.6) × 26 ≈ $374（0.37% 總資金）

**結論：以市價買入 26 股 MSFT，止損設在 $365.6**
""")

        st.markdown("### 每週一次（10 分鐘）")
        st.markdown("""
- **績效頁面**：看系統訊號的歷史準確率
- **回測頁面**：用最新數據重跑一次回測，確認策略仍有效
- **設定頁面**：確認自選清單是否需要更新
""")

    else:
        st.subheader("Daily 5-Minute Workflow")

        st.markdown("### Before Market Open (5 minutes)")
        st.markdown("""
```
1. Market Overview  →  Check Fear & Greed index + Macro Regime
2. AI Signals       →  Any new BUY signals? (need: Strength ≥ 0.4 AND Confidence ≥ 65%)
3. Risk Monitor     →  Confirm your drawdown is still in safe zone (< 8%)
```
""")

        st.markdown("### Signal Decision Flow")
        st.markdown("""
```
Signal appears
   ↓
earnings_warning present? → Yes → Skip
   ↓ No
breadth_regime = POOR? → Yes → Skip
   ↓ No
Strength ≥ 0.4 AND Confidence ≥ 65%? → No → Skip
   ↓ Yes
Backtest Sharpe > 1.0 for this symbol? → No → Proceed with caution
   ↓ Yes
Position ≤ 10%, set stop-loss → Enter
```
""")

        st.divider()
        st.subheader("Example: A Full Day's Decision Log")
        with st.expander("💡 Example: Alice's complete decision process on a trading day"):
            st.markdown("""
**9:00 AM (Before market open)**

**Step 1: Market Overview**
- Fear & Greed = **35 (Fear)** — slightly panicky market
- Macro Regime = **NEUTRAL** — no clear macro headwind
- Market Breadth = **HEALTHY** — most stocks above moving averages

**Step 2: AI Signals page**

Two signals appear:

| Symbol | Direction | Strength | Confidence | Risk Level |
|--------|-----------|----------|-----------|-----------|
| MSFT | BUY | +0.55 | 71% | MEDIUM |
| NVDA | BUY | +0.38 | 49% | HIGH |

**Step 3: Filter each signal**

**MSFT:**
- earnings_warning? ❌ None
- breadth_regime = POOR? ❌ No (HEALTHY)
- Strength ≥ 0.4? ✅ (0.55)
- Confidence ≥ 65%? ✅ (71%)
- → **Passes all filters — consider entering**

**NVDA:**
- Strength ≥ 0.4? ❌ (0.38 < 0.4)
- Confidence ≥ 65%? ❌ (49% < 65%)
- → **Skip immediately**

**Step 4: Confirm MSFT with backtest**
- Backtest result: Sharpe = 1.28, Max Drawdown = -13%
- ✅ Both metrics pass

**Step 5: Size the position**
- Total capital: $100,000
- MSFT price: $380
- Position: $100,000 × 10% = $10,000
- Shares: $10,000 ÷ $380 ≈ 26 shares
- ATR ≈ $7.2 → Stop-loss: $380 − ($7.2 × 2) = **$365.6**
- Max loss: ($380 − $365.6) × 26 ≈ $374 (0.37% of capital)

**Decision: Buy 26 shares of MSFT at market price. Set Stop-Loss at $365.6.**
""")

        st.markdown("### Weekly Review (10 minutes)")
        st.markdown("""
- **Performance page**: Check historical signal accuracy
- **Backtest page**: Re-run with latest data to confirm strategy is still valid
- **Settings page**: Update watchlist if needed
""")


# ════════════════════════════════════════════════════════════════════════
# Tab 6 — Common Mistakes
# ════════════════════════════════════════════════════════════════════════
with t6:
    if _zh:
        st.subheader("投資小白最常犯的錯誤")

        mistakes = [
            (
                "看到 BUY 就立刻買",
                "同時確認 Confidence ≥ 65% + Strength ≥ 0.4，三個條件缺一不可",
                "TSLA 出現 BUY，但 Strength=0.28、Confidence=45%。\n小明沒看這兩個數字直接買入。\n結果訊號很快反轉，3天內虧損 8%。\n✅ 正確：看到 BUY 先檢查這三個數字，不達標就跳過。",
            ),
            (
                "只看技術訊號，忽略宏觀",
                "結合 Macro Regime + Market Breadth + Sector 一起判斷，避免逆勢操作",
                "2022年初，某股票技術訊號顯示 BUY，Strength=0.55，看起來很強。\n但 Macro Regime=BEAR，Market Breadth=POOR（大盤進入熊市）。\n忽略宏觀的人買入後，股價繼續跌了 35%。\n✅ 正確：宏觀是大環境，逆流游泳很危險。BEAR 市盡量不做多。",
            ),
            (
                "把回測獲利當真實獲利",
                "回測是歷史參考，實際交易有滑點、情緒干擾，報酬會低於回測",
                "回測顯示 AAPL 年化報酬 +22%，小明滿心期待。\n但實際操作時，因為害怕而錯過進場、因為貪心而晚出場，\n實際年化只有 +8%。\n✅ 正確：把回測報酬打 6–7 折作為心理預期，已經算不錯了。",
            ),
            (
                "加密貨幣和股票用同樣倉位",
                "加密貨幣波動大 3–5 倍，倉位應縮小至股票的一半",
                "小明買 AAPL 用 10%（$10,000），買 BTC 也用 10%（$10,000）。\nBTC 一週內下跌 25%，損失 $2,500。\nAAPL 同期只跌 5%，損失 $500。\n✅ 正確：BTC 倉位應控制在 5%（$5,000），最大虧損才不會失控。",
            ),
            (
                "頻繁操作，追短線",
                "本系統為中長線設計（每日掃描），不適合當沖，頻繁操作會吃掉手續費",
                "小明每天進出 3–5 次，每次手續費 0.1%。\n一個月下來共交易 80 次，手續費合計 8%。\n即使策略本身賺了 5%，扣掉手續費實際虧損 3%。\n✅ 正確：耐心等好訊號，一個月操作 3–5 次就夠了。",
            ),
            (
                "訊號虧損後立刻加碼攤平",
                "系統有止損機制，觸發止損後應尊重，不要硬扛",
                "小明買 MSFT @ $380，止損設在 $365。\n股價跌到 $368，他覺得「快到止損了，應該反彈」，又加碼買了一倍。\n結果繼續跌到 $340，損失從 $375 變成 $2,600。\n✅ 正確：止損就是止損，不要和市場賭氣。觸發後平靜出場，等下一個機會。",
            ),
            (
                "忽略 Risk Level = HIGH 的訊號",
                "HIGH 風險的訊號代表各因子意見分歧，即使 Direction 是 BUY 也建議跳過",
                "某標的顯示 BUY，Strength=0.51，Confidence=67%，但 Risk Level=HIGH。\n小明覺得 Strength 和 Confidence 都達標，就進場了。\n結果因為因子分歧，訊號很不穩定，3天後反轉虧損。\n✅ 正確：Risk Level=HIGH 是額外的警示，三個條件都達標還不夠，HIGH 就跳過。",
            ),
            (
                "不設止損就進場",
                "每筆交易前必須設定止損價，最大接受虧損 ≤ 5% 總資金",
                "小明買入某股票，心想「反正是長線，不用止損」。\n股票公司突然爆出負面消息，一天跌 40%。\n沒有止損的他，損失了 $8,000（8% 總資金）。\n✅ 正確：長線也需要止損，意外永遠來得突然。止損是保護本金的最後防線。",
            ),
        ]

        for i, (wrong, right, example) in enumerate(mistakes, 1):
            with st.expander(f"❌ 誤區 {i}：{wrong}"):
                st.success(f"✅ 正確做法：{right}")
                st.divider()
                st.markdown("**📖 實際情境：**")
                st.markdown(example)

    else:
        st.subheader("Most Common Beginner Mistakes")

        mistakes = [
            (
                "Buying immediately on every BUY signal",
                "Confirm all three: Direction = BUY, Confidence ≥ 65%, Strength ≥ 0.4",
                "TSLA shows BUY, but Strength=0.28 and Confidence=45%.\n"
                "Bob ignores these numbers and buys immediately.\n"
                "The signal reverses quickly — he loses 8% in 3 days.\n"
                "✅ Correct: Always check the three numbers first. If any fails, skip.",
            ),
            (
                "Relying only on technical signals, ignoring macro",
                "Combine with Macro Regime, Market Breadth, and Sector — avoid trading against the trend",
                "In early 2022, a stock shows a strong BUY signal (Strength=0.55).\n"
                "But Macro Regime=BEAR and Market Breadth=POOR — the market has entered a bear trend.\n"
                "Those who ignored the macro bought in and lost 35% as the market continued falling.\n"
                "✅ Correct: Macro is the tide. Don't swim against it. Avoid longs in BEAR regime.",
            ),
            (
                "Treating backtest returns as real returns",
                "Backtests are historical references. Expect real results 30–40% lower due to slippage and emotions",
                "Backtest shows AAPL annual return of +22%. Bob is excited.\n"
                "But in real trading, fear makes him miss entries and greed makes him exit late.\n"
                "His actual annual return is only +8%.\n"
                "✅ Correct: Mentally discount backtest returns by 30–40% for a realistic expectation.",
            ),
            (
                "Using the same position size for crypto and stocks",
                "Crypto is 3–5× more volatile — use half the position size",
                "Bob buys AAPL with 10% ($10,000) and BTC with 10% ($10,000).\n"
                "BTC drops 25% in a week — loss of $2,500.\n"
                "AAPL only drops 5% — loss of $500.\n"
                "✅ Correct: BTC position should be 5% ($5,000) to keep max loss manageable.",
            ),
            (
                "Frequent short-term trading",
                "This system is designed for medium-to-long term. High frequency eats returns through commissions",
                "Bob trades 3–5 times per day. Each trade costs 0.1% commission.\n"
                "80 trades in a month = 8% in fees.\n"
                "Strategy made 5%, but after fees: -3% net loss.\n"
                "✅ Correct: Wait for quality signals. 3–5 trades per month is enough.",
            ),
            (
                "Adding to a losing position after a stop is hit",
                "Respect the stop-loss. Don't average down after it triggers",
                "Bob buys MSFT @ $380, stop-loss at $365.\n"
                "Price drops to $368. He thinks 'almost at my stop, it'll bounce' and doubles down.\n"
                "Price continues to $340 — loss grows from $375 to $2,600.\n"
                "✅ Correct: A stop is a stop. Exit calmly and wait for the next opportunity.",
            ),
            (
                "Ignoring Risk Level = HIGH signals",
                "HIGH risk means factors strongly disagree. Even if Direction=BUY, skip it",
                "A symbol shows BUY, Strength=0.51, Confidence=67% — both pass thresholds.\n"
                "But Risk Level=HIGH. Bob enters anyway.\n"
                "The conflicting factors cause instability — the signal reverses in 3 days at a loss.\n"
                "✅ Correct: Risk Level=HIGH is an additional warning. All metrics must pass, including this one.",
            ),
            (
                "Entering without a stop-loss",
                "Always set a stop-loss before entering. Max acceptable loss: ≤ 5% of capital",
                "Bob buys a stock, thinking 'it's a long-term hold, I don't need a stop'.\n"
                "The company releases shocking negative news — stock drops 40% in one day.\n"
                "Without a stop, he loses $8,000 (8% of total capital).\n"
                "✅ Correct: Even long-term positions need stops. Surprises always come without warning.",
            ),
        ]

        for i, (wrong, right, example) in enumerate(mistakes, 1):
            with st.expander(f"❌ Mistake {i}: {wrong}"):
                st.success(f"✅ Correct approach: {right}")
                st.divider()
                st.markdown("**📖 Real-world scenario:**")
                st.markdown(example)

    st.divider()
    if _zh:
        st.caption("📌 最重要的一句話：**控制好每筆的虧損上限，比追求更高獲利更重要。** 本系統是輔助決策工具，不是自動提款機。")
    else:
        st.caption("📌 Most important rule: **Limiting losses on each trade matters more than maximising gains.** This system is a decision-support tool, not an ATM.")
