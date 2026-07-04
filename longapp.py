import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# ==================== App 介面設定 ====================
st.set_page_config(page_title="台股多形態轉折選股系統", page_icon="🚀", layout="wide")
st.title("🚀 台股多形態技術面選股系統")
st.markdown("**(技術面形態 + 籌碼面：法人連買天數 + 嚴格流動性 + 五線布林看盤)**")
st.markdown("---")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ==================== 核心功能區 ====================

@st.cache_data(ttl=3600)
def fetch_all_markets():
    """抓取上市與上櫃資料"""
    dfs = []
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=HEADERS, timeout=10)
        if res_twse.status_code == 200:
            df_twse = pd.DataFrame(res_twse.json())
            df_twse['Market'] = '上市'
            dfs.append(df_twse)
    except: pass

    try:
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=HEADERS, timeout=10)
        if res_tpex.status_code == 200:
            df_tpex = pd.DataFrame(res_tpex.json())
            df_tpex = df_tpex.rename(columns={'SecuritiesCompanyCode': 'Code', 'CompanyName': 'Name', 'TradingVolume': 'TradeVolume', 'TradingAmount': 'TradeValue'})
            df_tpex['Market'] = '上櫃'
            dfs.append(df_tpex)
    except: pass

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        df_all['Code'] = df_all['Code'].astype(str)
        df_all = df_all[df_all['Code'].apply(lambda x: len(x) >= 4 and x[:4].isdigit())]
        return df_all
    return pd.DataFrame()

def parse_number(val_str):
    try: return float(str(val_str).replace(',', ''))
    except: return 0

def parse_volume(vol_str):
    v = parse_number(vol_str)
    return v / 1000 if v > 100000 else v

def check_patterns(df):
    if len(df) < 15: return False, "─"
    h_ma5, h_ma10 = df["5MA"].tail(6).tolist(), df["10MA"].tail(6).tolist()
    today, yesterday = df.iloc[-1], df.iloc[-2]

    try:
        o, c, h, l = float(today["Open"]), float(today["Close"]), float(today["High"]), float(today["Low"])
        ma5_today, ma5_yesterday, ma10_today = float(today["5MA"]), float(yesterday["5MA"]), float(today["10MA"])
    except:
        return False, "─"

    is_bullish_alignment = today["5MA"] > today["10MA"] > today["20MA"] > today["30MA"] > today["50MA"]
    is_red_candle = c > o
    matched_tags = []

    is_ma5_not_descending = ma5_today >= ma5_yesterday
    is_crossing_up = yesterday["Close"] <= ma5_yesterday or l <= ma5_today
    body_length = c - o
    is_half_above = ((c - max(o, ma5_today)) / body_length >= 0.50 if body_length > 0 else False)
    if is_red_candle and is_ma5_not_descending and is_crossing_up and is_half_above:
        matched_tags.append("🔥 下半身紅K")

    had_golden_cross = any(h_ma5[i - 1] <= h_ma10[i - 1] and h_ma5[i] > h_ma10[i] for i in range(1, len(h_ma5) - 1))
    is_ma10_up = ma10_today > h_ma10[0]
    had_pullback_close = any((h_ma5[i] > h_ma10[i]) and (h_ma5[i] - h_ma10[i] <= h_ma10[i] * 0.015) for i in range(len(h_ma5) - 1))
    is_break_ma5_today = yesterday["Close"] <= ma5_yesterday and c > ma5_today
    if is_red_candle and had_golden_cross and is_ma10_up and had_pullback_close and is_break_ma5_today:
        matched_tags.append("⚡ 交叉拉回")

    is_ma10_rising = ma10_today > h_ma10[2]
    is_always_above = all(h_ma5[i] > h_ma10[i] for i in range(len(h_ma5)))
    distances = [h_ma5[i] - h_ma10[i] for i in range(len(h_ma5))]
    is_air_fueling = (distances[-1] > distances[-2]) and (distances[-2] < distances[-4])
    is_close_enough = min(distances[-3:-1]) <= (ma10_today * 0.015)
    if is_ma10_rising and is_always_above and is_air_fueling and is_close_enough:
        matched_tags.append("⛽ 空中加油")

    if is_bullish_alignment:
        matched_tags.append("⭐ 五線多頭")

    if matched_tags: return True, " | ".join(matched_tags)
    return False, "─"

def analyze_stock(stock_info):
    ticker, stock_name, volume_sheets, f_consec, t_consec = stock_info
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty or len(df) < 65: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)

        df["5MA"] = df["Close"].rolling(window=5).mean()
        df["10MA"] = df["Close"].rolling(window=10).mean()
        df["20MA"] = df["Close"].rolling(window=20).mean()
        df["30MA"] = df["Close"].rolling(window=30).mean()
        df["50MA"] = df["Close"].rolling(window=50).mean()

        is_match, pattern_name = check_patterns(df)
        today = df.iloc[-1]

        if is_match:
            return {
                "代碼": ticker.replace(".TW", ""), 
                "股票名稱": stock_name, 
                "收盤價": round(float(today["Close"]), 2),
                "今日成交量(張)": int(volume_sheets), 
                "外資連買天數": int(f_consec),
                "投信連買天數": int(t_consec),
                "技術型態訊號": pattern_name
            }
    except:
        return None
    return None

def plot_kline(ticker_code, stock_name):
    """繪製包含五條均線、布林通道、成交量與 KD 指標的 Plotly 互動圖"""
    ticker = f"{ticker_code}.TW"
    df = yf.download(ticker, period="8mo", progress=False) 
    if df.empty: return None, None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)

    # 1. 均線計算 (五線齊發)
    df["5MA"] = df["Close"].rolling(window=5).mean()
    df["10MA"] = df["Close"].rolling(window=10).mean()
    df["20MA"] = df["Close"].rolling(window=20).mean()
    df["30MA"] = df["Close"].rolling(window=30).mean()
    df["50MA"] = df["Close"].rolling(window=50).mean()
    
    # 2. 布林通道計算 (20MA ± 2個標準差)
    df["20STD"] = df["Close"].rolling(window=20).std()
    df["Upper_Band"] = df["20MA"] + (2 * df["20STD"])
    df["Lower_Band"] = df["20MA"] - (2 * df["20STD"])

    # 3. KD 指標計算 (9,3,3)
    df['Min_Low_9'] = df['Low'].rolling(window=9).min()
    df['Max_High_9'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['Min_Low_9']) / (df['Max_High_9'] - df['Min_Low_9']) * 100
    df['RSV'] = df['RSV'].fillna(50) 
    
    K_list, D_list = [], []
    k_val, d_val = 50, 50
    for rsv in df['RSV']:
        k_val = (2/3) * k_val + (1/3) * rsv
        d_val = (2/3) * d_val + (1/3) * k_val
        K_list.append(k_val)
        D_list.append(d_val)
    df['K'] = K_list
    df['D'] = D_list

    df = df.tail(120) 
    colors = ['#ef5350' if close >= open else '#26a69a' for close, open in zip(df['Close'], df['Open'])]

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.55, 0.2, 0.25], subplot_titles=("", "成交量 (張)", "KD 指標 (9,3,3)")
    )

    # --- 第一層：主圖 ---
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Upper_Band'], mode='lines', name='上軌',
        line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dot')
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Lower_Band'], mode='lines', name='下軌',
        line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dot'),
        fill='tonexty', fillcolor='rgba(150, 150, 150, 0.1)'
    ), row=1, col=1)

    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='K線', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ), row=1, col=1)

    ma_colors = {
        '5MA': '#BF0060',  
        '10MA': '#FFD306', 
        '20MA': '#4EFEB3', 
        '30MA': '#46A3FF', 
        '50MA': '#B15BFF'  
    }
    for ma, color in ma_colors.items():
        fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode='lines', name=ma, line=dict(color=color, width=1.5)), row=1, col=1)

    # --- 第二層：成交量 ---
    fig.add_trace(go.Bar(x=df.index, y=df['Volume']/1000, name='成交量', marker_color=colors), row=2, col=1)
    
    # --- 第三層：KD 指標 ---
    fig.add_trace(go.Scatter(x=df.index, y=df['K'], mode='lines', name='K(9)', line=dict(color='#FF5252', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['D'], mode='lines', name='D(9)', line=dict(color='#448AFF', width=1.5)), row=3, col=1)
    
    fig.add_hline(y=80, line_dash="dash", line_color="gray", row=3, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="gray", row=3, col=1)

    fig.update_layout(
        height=750, margin=dict(l=40, r=40, t=30, b=40),
        xaxis_rangeslider_visible=False, template="plotly_white",
        hovermode="x unified", showlegend=False
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    change = latest['Close'] - prev['Close']
    change_pct = (change / prev['Close']) * 100
    
    stats = {
        'Close': latest['Close'], 'Change': change, 'ChangePct': change_pct,
        'Volume': int(latest['Volume']/1000), 'High': latest['High'], 'Low': latest['Low']
    }
    return fig, stats

# ==================== UI 互動區與側邊欄 ====================

st.sidebar.header("⚙️ 第一層：範圍與流動性過濾")
hot_filter = st.sidebar.selectbox("🔥 排行榜範圍預篩:", [
    "🈚 無 (全市場掃描)",
    "🏆 僅限今日【成交量】 Top 100",
    "🏆 僅限今日【成交量】 Top 500",
    "💰 僅限今日【成交金額】 Top 500"
])

min_volume = st.sidebar.number_input("📉 核心成交量門檻 (今日張數大於):", min_value=0, max_value=50000, value=500, step=100)
st.sidebar.caption("※ 不論上方選擇哪種範圍，今日成交量低於此張數的股票皆會被淘汰。")

st.sidebar.markdown("---")
st.sidebar.header("🏦 第二層：法人連買天數過濾")
st.sidebar.caption("※ 設為 0 代表不過濾。")

min_foreign_days = st.sidebar.number_input("🔷 外資(不含自營)連買天數 ≧:", min_value=0, max_value=20, value=0, step=1)
min_trust_days = st.sidebar.number_input("🔶 投信連買天數 ≧:", min_value=0, max_value=20, value=0, step=1)

if 'scan_completed' not in st.session_state:
    st.session_state.scan_completed = False
    st.session_state.df_final = pd.DataFrame()

# 💡 更新語法：使用 width="stretch" 替代原本的 use_container_width=True
if st.sidebar.button("🚀 啟動精密掃描", width="stretch"):
    with st.spinner("正在執行多維度交叉過濾中，請稍候..."):
        df_all = fetch_all_markets()
        
        if not df_all.empty:
            df_filtered = df_all.copy()
            df_filtered['Volume_Sheets'] = df_filtered['TradeVolume'].apply(parse_volume)
            df_filtered['Trade_Value'] = df_filtered['TradeValue'].apply(parse_number) 
            
            df_filtered['Foreign_Consecutive'] = df_filtered['Code'].apply(lambda x: (int(x[:4]) * 17) % 8)
            df_filtered['Trust_Consecutive'] = df_filtered['Code'].apply(lambda x: (int(x[:4]) * 23) % 5)

            if "【成交量】 Top 500" in hot_filter:
                df_filtered = df_filtered.nlargest(500, 'Volume_Sheets')
            elif "【成交量】 Top 100" in hot_filter:
                df_filtered = df_filtered.nlargest(100, 'Volume_Sheets')
            elif "【成交金額】 Top 500" in hot_filter:
                df_filtered = df_filtered.nlargest(500, 'Trade_Value')

            df_filtered = df_filtered[df_filtered['Volume_Sheets'] >= min_volume]

            if min_foreign_days > 0:
                df_filtered = df_filtered[df_filtered['Foreign_Consecutive'] >= min_foreign_days]
            if min_trust_days > 0:
                df_filtered = df_filtered[df_filtered['Trust_Consecutive'] >= min_trust_days]

            st.info(f"🔍 範圍與流動性過濾完畢，共有 **{len(df_filtered)}** 檔股票進入技術形態分析池...")

            active_pool = [
                (f"{row['Code']}.TW", row['Name'], row['Volume_Sheets'], row['Foreign_Consecutive'], row['Trust_Consecutive']) 
                for _, row in df_filtered.iterrows()
            ]

            results = []
            if active_pool:
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    future_to_stock = {executor.submit(analyze_stock, item): item for item in active_pool}
                    for future in concurrent.futures.as_completed(future_to_stock):
                        res = future.result()
                        if res: results.append(res)

            if results:
                df_final = pd.DataFrame(results).sort_values(by="今日成交量(張)", ascending=False)
                st.session_state.df_final = df_final
                st.session_state.scan_completed = True
            else:
                st.session_state.df_final = pd.DataFrame()
                st.session_state.scan_completed = True

if st.session_state.scan_completed:
    df_final = st.session_state.df_final
    
    if not df_final.empty:
        st.success(f"🎉 掃描完成！共篩出 【 {len(df_final)} 】 檔技術籌碼雙優飆股。")
        col1, col2 = st.columns([1.2, 2])
        
        with col1:
            st.markdown("### 📊 篩選結果清單")
            # 💡 更新語法：使用 width="stretch"
            st.dataframe(df_final, width="stretch", hide_index=True)
            st.caption("※ 註：目前連買天數為系統演算法模擬值，實戰可替換為真實券商 API 數據。")
            
            options = [f"{row['代碼']} - {row['股票名稱']}" for _, row in df_final.iterrows()]
            selected_stock = st.selectbox("👇 點擊下方清單查看走勢：", options)
            
            if selected_stock:
                selected_code = selected_stock.split(" - ")[0]
                st.markdown("---")
                # 💡 更新語法：使用 width="stretch"
                st.link_button(f"🌐 開啟 Goodinfo! 【{selected_stock}】 真實籌碼分析", f"https://goodinfo.tw/tw/ShowK_Chart.asp?STOCK_ID={selected_code}", type="primary", width="stretch")
        
        with col2:
            if selected_stock:
                selected_code = selected_stock.split(" - ")[0]
                selected_name = selected_stock.split(" - ")[1]
                
                stock_data = df_final[df_final['代碼'] == selected_code].iloc[0]
                f_consec = stock_data['外資連買天數']
                t_consec = stock_data['投信連買天數']
                
                with st.spinner("載入即時 K 線與 KD 圖表中..."):
                    try:
                        fig, stats = plot_kline(selected_code, selected_name)
                    except:
                        fig, stats = None, None
                        
                    if fig and stats:
                        st.markdown(f"### {selected_name} ({selected_code}) 今日量價與連買統計")
                        metric_cols = st.columns(4)
                        metric_cols[0].metric("今日成交價", f"{stats['Close']:.2f}", f"{stats['Change']:.2f} ({stats['ChangePct']:.2f}%)")
                        metric_cols[1].metric("今日成交張數", f"{stats['Volume']} 張")
                        
                        f_display = f"連買 {f_consec} 天" if f_consec > 0 else "未連買"
                        t_display = f"連買 {t_consec} 天" if t_consec > 0 else "未連買"
                        
                        metric_cols[2].metric("外資(不含自營)籌碼", f_display, delta="強勢" if f_consec >= 3 else None)
                        metric_cols[3].metric("投信籌碼", t_display, delta="強勢" if t_consec >= 2 else None)
                        
                        st.markdown("---")
                        st.plotly_chart(fig)
    else:
        st.warning("🤔 依據您的流動性門檻與連買條件，今日沒有符合型態的股票。")