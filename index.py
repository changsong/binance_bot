"""
交易历史展示页面 - 使用 Streamlit
运行方式: streamlit run index.py
"""
import os
import json
import time
import streamlit as st
import pandas as pd
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 页面配置
st.set_page_config(
    page_title="交易历史 - Binance Bot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 交易历史文件路径
TRADE_HISTORY_FILE = os.path.join(BASE_DIR, "logs", "trade_history.json")
# 回测结果文件路径
BACKTEST_HISTORY_FILE = os.path.join(BASE_DIR, "logs", "backtest_history.json")

# 从环境变量读取配置
BINANCE_MODE = os.getenv("BINANCE_MODE", "testnet").lower()
TRADE_TYPE = os.getenv("TRADE_TYPE", "futures").lower()
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")

@st.cache_data(ttl=60)  # 缓存60秒
def load_trade_history() -> list:
    """加载交易历史数据"""
    try:
        if not os.path.exists(TRADE_HISTORY_FILE):
            return []
        
        with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        
        return history if isinstance(history, list) else []
    except Exception as e:
        st.error(f"加载交易历史失败: {e}")
        return []

@st.cache_data(ttl=60)
def load_backtest_history() -> list:
    """加载回测批次数据"""
    try:
        if not os.path.exists(BACKTEST_HISTORY_FILE):
            return []
        with open(BACKTEST_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history if isinstance(history, list) else []
    except Exception as e:
        st.error(f"加载回测数据失败: {e}")
        return []

def format_timestamp(timestamp: str) -> str:
    """格式化时间戳"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp

def format_number(num) -> str:
    """格式化数字"""
    if num is None:
        return "-"
    try:
        return f"{float(num):,.8f}".rstrip('0').rstrip('.')
    except:
        return str(num)

def get_side_color(side: str) -> str:
    """获取方向颜色"""
    if side == "LONG":
        return "🟢"
    elif side == "SHORT":
        return "🔴"
    return "⚪"

def parse_numeric(value) -> Optional[float]:
    """解析带符号/百分号的数字字符串"""
    if value is None:
        return None
    try:
        s = str(value).strip()
        if not s:
            return None
        s = s.replace("%", "").replace("+", "").replace("−", "-")
        return float(s)
    except Exception:
        return None

# ================= 主界面 =================
st.title("📊 交易历史与回测分析")
st.markdown("---")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置信息")
    st.info(f"**模式:** {BINANCE_MODE.upper()}")
    st.info(f"**交易类型:** {TRADE_TYPE.upper()}")
    st.info(f"**标的:** {SYMBOL}")
    
    st.markdown("---")
    st.header("🔄 刷新设置")
    auto_refresh = st.checkbox("自动刷新", value=True)
    refresh_interval = st.slider("刷新间隔（秒）", 10, 300, 10, 10)
    
    st.markdown("---")
    if st.button("🔄 手动刷新", use_container_width=True):
        st.rerun()
    
    st.markdown("---")
    st.markdown("### 📝 说明")
    st.caption("""
    - 页面会自动刷新显示最新交易记录
    - 支持按时间、方向、标的筛选
    - 可以导出为 CSV 文件
    """)

# 加载数据
history = load_trade_history()

# 页面切换（避免 tab 切换导致自动刷新回到默认页）
page = st.radio("页面", ["实时交易历史", "回测结果分析"], horizontal=True, key="page")

if page == "实时交易历史":
    st.header("实时交易历史")
    if not history:
        st.warning("⚠️ 暂无交易记录")
        st.info("交易记录将在这里显示")
    else:
        # 转换为 DataFrame
        df = pd.DataFrame(history)
        
        # 数据预处理
        if 'timestamp' in df.columns:
            df['formatted_time'] = df['timestamp'].apply(format_timestamp)
            df = df.sort_values('timestamp', ascending=False)

        # 一对二配对标记（ENTRY 对应 TP1/TP2）
        if 'action' in df.columns and 'entry_id' in df.columns:
            df['pair_status'] = ""
            # 统计每个 entry_id 的退出原因
            exits = df[df['action'] == 'EXIT'] if 'EXIT' in df['action'].values else pd.DataFrame()
            exit_map = {}
            if not exits.empty and 'exit_reason' in exits.columns:
                for _, row in exits.iterrows():
                    eid = row.get('entry_id')
                    reason = row.get('exit_reason')
                    if eid:
                        exit_map.setdefault(eid, set()).add(str(reason))

            def _pair_status(row):
                if row.get('action') == 'ENTRY':
                    eid = row.get('entry_id')
                    reasons = exit_map.get(eid, set())
                    has_tp1 = 'TP1' in reasons
                    has_tp2 = 'TP2' in reasons
                    if has_tp1 and has_tp2:
                        return "一对二✅"
                    if has_tp1 and not has_tp2:
                        return "TP1✅ / TP2⏳"
                    if has_tp2 and not has_tp1:
                        return "TP1⏳ / TP2✅"
                    return "未退出"
                if row.get('action') == 'EXIT':
                    reason = row.get('exit_reason') or "EXIT"
                    return f"{reason}"
                return ""

            df['pair_status'] = df.apply(_pair_status, axis=1)
        
        # 统计信息
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总记录数", len(df))
        with col2:
            long_count = len(df[df.get('side', '') == 'LONG']) if 'side' in df.columns else 0
            st.metric("做多次数", long_count)
        with col3:
            short_count = len(df[df.get('side', '') == 'SHORT']) if 'side' in df.columns else 0
            st.metric("做空次数", short_count)
        with col4:
            unique_symbols = df['symbol'].nunique() if 'symbol' in df.columns else 0
            st.metric("交易标的数", unique_symbols)
        
        st.markdown("---")
        
        # 筛选器
        col1, col2, col3 = st.columns(3)
        with col1:
            if 'side' in df.columns:
                sides = ['全部'] + list(df['side'].unique())
                selected_side = st.selectbox("筛选方向", sides)
            else:
                selected_side = '全部'
        
        with col2:
            if 'symbol' in df.columns:
                symbols = ['全部'] + sorted(df['symbol'].unique().tolist())
                selected_symbol = st.selectbox("筛选标的", symbols)
            else:
                selected_symbol = '全部'
        
        with col3:
            limit = st.number_input("显示条数", min_value=10, max_value=1000, value=100, step=10)
        
        # 应用筛选
        filtered_df = df.copy()
        if selected_side != '全部' and 'side' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['side'] == selected_side]
        if selected_symbol != '全部' and 'symbol' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['symbol'] == selected_symbol]
        
        filtered_df = filtered_df.head(limit)
        
        st.markdown("---")
        
        # 显示数据表格
        if len(filtered_df) > 0:
            # 准备显示的列
            display_columns = []
            column_config = {}
            
            if 'formatted_time' in filtered_df.columns:
                display_columns.append('formatted_time')
                column_config['formatted_time'] = st.column_config.TextColumn("时间", width="medium")
            elif 'timestamp' in filtered_df.columns:
                display_columns.append('timestamp')
                column_config['timestamp'] = st.column_config.TextColumn("时间", width="medium")
            
            if 'symbol' in filtered_df.columns:
                display_columns.append('symbol')
                column_config['symbol'] = st.column_config.TextColumn("标的", width="small")
            
            if 'side' in filtered_df.columns:
                display_columns.append('side')
                column_config['side'] = st.column_config.TextColumn("方向", width="small")
            
            if 'qty' in filtered_df.columns:
                display_columns.append('qty')
                column_config['qty'] = st.column_config.NumberColumn("数量", format="%.8f")
            
            if 'entry' in filtered_df.columns:
                display_columns.append('entry')
                column_config['entry'] = st.column_config.NumberColumn("入场价", format="%.2f")
            
            if 'stop' in filtered_df.columns:
                display_columns.append('stop')
                column_config['stop'] = st.column_config.NumberColumn("止损价", format="%.2f")

            if 'tp1' in filtered_df.columns:
                display_columns.append('tp1')
                column_config['tp1'] = st.column_config.NumberColumn("止盈1", format="%.2f")

            if 'tp2' in filtered_df.columns:
                display_columns.append('tp2')
                column_config['tp2'] = st.column_config.NumberColumn("止盈2", format="%.2f")

            if 'score' in filtered_df.columns:
                display_columns.append('score')
                column_config['score'] = st.column_config.NumberColumn("评分", format="%.2f")

            if 'action' in filtered_df.columns:
                display_columns.append('action')
                column_config['action'] = st.column_config.TextColumn("动作", width="small")

            if 'exit_reason' in filtered_df.columns:
                display_columns.append('exit_reason')
                column_config['exit_reason'] = st.column_config.TextColumn("退出原因", width="small")

            if 'entry_id' in filtered_df.columns:
                display_columns.append('entry_id')
                column_config['entry_id'] = st.column_config.TextColumn("入场ID", width="medium")

            if 'pair_status' in filtered_df.columns:
                display_columns.append('pair_status')
                column_config['pair_status'] = st.column_config.TextColumn("配对状态", width="small")
            
            if 'message' in filtered_df.columns:
                display_columns.append('message')
                column_config['message'] = st.column_config.TextColumn("消息", width="large")
            
            # 显示表格
            st.dataframe(
                filtered_df[display_columns],
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
                height=600
            )
            
            # 导出功能
            st.markdown("---")
            col1, col2 = st.columns([1, 4])
            with col1:
                csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 导出为 CSV",
                    data=csv,
                    file_name=f"trade_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.info("没有符合筛选条件的记录")
        
    # 自动刷新（使用 JavaScript）
    if auto_refresh:
        st.markdown(f"""
        <script>
            setTimeout(function(){{
                window.location.reload();
            }}, {refresh_interval * 1000});
        </script>
        <div style="text-align: center; padding: 10px; background-color: #f0f2f6; border-radius: 5px; margin-top: 20px;">
            ⏱️ 页面将在 {refresh_interval} 秒后自动刷新...
        </div>
        """, unsafe_allow_html=True)

else:
    st.header("回测结果分析")

    backtests = load_backtest_history()
    if not backtests:
        st.info("暂无回测批次数据")
    else:
        bt_df = pd.DataFrame(backtests)

        batch_ids = []
        if "batchId" in bt_df.columns:
            batch_ids = sorted(bt_df["batchId"].dropna().unique().tolist())

        # 构造批次显示名称：batch_id + strategyName
        strategy_map = {}
        if batch_ids and "strategyName" in bt_df.columns:
            for batch_id, group in bt_df.groupby("batchId"):
                names = group["strategyName"].dropna().unique().tolist()
                if names:
                    strategy_map[batch_id] = names[0]

        def _batch_label(batch_id: str) -> str:
            name = strategy_map.get(batch_id)
            return f"{batch_id} | {name}" if name else batch_id

        if batch_ids:
            selected_batch = st.selectbox(
                "选择回测批次",
                batch_ids,
                index=len(batch_ids) - 1,
                format_func=_batch_label
            )
            batch_df = bt_df[bt_df["batchId"] == selected_batch].copy()
        else:
            selected_batch = None
            batch_df = bt_df.copy()

        # 解析数值字段
        metric_cols = [
            "totalPnL",
            "maxEquityDrawdown",
            "totalTrades",
            "winningTradesPercent",
            "profitFactor",
            "sharpeRatio"
        ]
        for col in metric_cols:
            if col in batch_df.columns:
                batch_df[col] = batch_df[col].apply(parse_numeric)

        st.dataframe(batch_df, use_container_width=True, hide_index=True, height=400)

        # 批次对比
        if len(batch_ids) >= 2:
            st.subheader("📊 批次对比")
            col1, col2 = st.columns(2)
            with col1:
                batch_a = st.selectbox(
                    "批次 A",
                    batch_ids,
                    index=len(batch_ids) - 1,
                    key="batch_a",
                    format_func=_batch_label
                )
            with col2:
                batch_b = st.selectbox(
                    "批次 B",
                    batch_ids,
                    index=len(batch_ids) - 2,
                    key="batch_b",
                    format_func=_batch_label
                )

            df_a = bt_df[bt_df["batchId"] == batch_a].copy()
            df_b = bt_df[bt_df["batchId"] == batch_b].copy()
            for col in metric_cols:
                if col in df_a.columns:
                    df_a[col] = df_a[col].apply(parse_numeric)
                if col in df_b.columns:
                    df_b[col] = df_b[col].apply(parse_numeric)

            if "symbol" in df_a.columns and "symbol" in df_b.columns:
                common_symbols = sorted(set(df_a["symbol"]) & set(df_b["symbol"]))
            else:
                common_symbols = []

            if not common_symbols:
                st.warning("两个批次没有相同的标的可对比")
            else:
                compare_rows = []
                for sym in common_symbols:
                    row_a = df_a[df_a["symbol"] == sym].iloc[-1].to_dict()
                    row_b = df_b[df_b["symbol"] == sym].iloc[-1].to_dict()
                    row = {"symbol": sym}
                    for col in metric_cols:
                        a_val = row_a.get(col)
                        b_val = row_b.get(col)
                        row[f"{col}_A"] = a_val
                        row[f"{col}_B"] = b_val
                        if a_val is not None and b_val is not None:
                            row[f"{col}_diff"] = b_val - a_val
                    compare_rows.append(row)

                compare_df = pd.DataFrame(compare_rows)
                st.dataframe(compare_df, use_container_width=True, hide_index=True, height=400)

                chart_metric = st.selectbox("对比指标（折线图）", metric_cols)
                chart_df = compare_df.set_index("symbol")[[f"{chart_metric}_A", f"{chart_metric}_B"]]
                st.line_chart(chart_df)

# 页脚
st.markdown("---")
st.caption(f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

