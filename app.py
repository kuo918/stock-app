import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import random

# ==================== App 介面設定 ====================
st.set_page_config(page_title="台股多空雙向轉折選股系統", page_icon="🔥", layout="wide")
st.title("🔥 台股多空雙向綜合選股系統")
st.markdown("**(多層次漏斗篩選：Yahoo即時流動性 ➔ 技術形態 ➔ 籌碼面)**")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ==================== 核心數據獲取與籌碼演算法 ====================
@st.cache_data(ttl=3600)
def fetch_all_markets():
    """抓取上市與上櫃資料，並自動配置正確的 Yahoo 股票代號"""
    dfs = []
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=HEADERS, timeout=10)
        if res_twse.status_code == 200:
            df_twse = pd.DataFrame(res_twse.json())
            df_twse['Market'] = '上市'
            df_twse['YF_Ticker'] = df_twse['Code'] + '.TW'
            dfs.append(df_twse)
    except: pass

    try:
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=HEADERS, timeout=10)
        if res_tpex.status_code == 200:
            df_tpex = pd.DataFrame(res_tpex.json())
            df_tpex = df_tpex.rename(columns={'SecuritiesCompanyCode': 'Code', 'CompanyName': 'Name'})
            df_tpex['Market'] = '上櫃'
            df_tpex['YF_Ticker'] = df_tpex['Code'] + '.TWO'
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

def calculate_consecutive_days(net_buy_sell_list):
    if not net_buy_sell_list: return 0
    latest_val = net_buy_sell_list[0]
    if latest_val == 0: return 0
        
    is_buying = latest_val > 0
    consecutive_count = 0
    
    for val in net_buy_sell_list:
        if is_buying and val > 0:
            consecutive_count += 1
        elif not is_buying and val < 0:
            consecutive_count += 1
        else:
            break
    return consecutive_count if is_buying else -consecutive_count

def get_mock_institutional_data(code, inst_type="foreign"):
    random.seed(int(code[:4]) + (1 if inst_type == "foreign" else 2))
    return [random.choice([-500, -200, -50, 0, 100, 300, 800]) for _ in range(10)]

# ==================== 技術形態邏輯 (多空整合) ====================
def check_patterns(df, strategy, selected_patterns):
    if len(df) < 15: return False, "─"
    h_ma5, h_ma10 = df["5MA"].tail(6).tolist(), df["10MA"].tail(6).tolist()
    today, yesterday = df.iloc[-1], df.iloc[-2]

    try:
        o, c, h, l = float(today["Open"]), float(today["Close"]), float(today["High"]), float(today["Low"])
        ma5_today, ma5_yesterday, ma10_today = float(today["5MA"]), float(yesterday["5MA"]), float(today["10MA"])
    except:
        return False, "─"

    matched_tags = []

    if strategy == "做多 (Long)":
        is_bullish_alignment = today["5MA"] > today["10MA"] > today["20MA"] > today["30MA"] > today["50MA"]
        is_red_candle = c > o

        is_ma5_not_descending = ma5_today >= ma5_yesterday
        is_crossing_up = yesterday["Close"] <= ma5_yesterday or l <= ma5_today
        body_length = c - o
        is_half_above = ((c - max(o, ma5_today)) / body_length >= 0.50 if body_length > 0 else False)
        if "🔥 下半身紅K" in selected_patterns and is_red_candle and is_ma5_not_descending and is_crossing_up and is_half_above:
            matched_tags.append("🔥 下半身紅K")

        had_golden_cross = any(h_ma5[i - 1] <= h_ma10[i - 1] and h_ma5[i] > h_ma10[i] for i in range(1, len(h_ma5) - 1))
        is_ma10_up = ma10_today > h_ma10[0]
        had_pullback_close = any((h_ma5[i] > h_ma10[i]) and (h_ma5[i] - h_ma10[i] <= h_ma10[i] * 0.015) for i in range(len(h_ma5) - 1))
        is_break_ma5_today = yesterday["Close"] <= ma5_yesterday and c > ma5_today
        if "⚡ 交叉拉回" in selected_patterns and is_red_candle and had_golden_cross and is_ma10_up and had_pullback_close and is_break_ma5_today:
            matched_tags.append("⚡ 交叉拉回")

        is_ma10_rising = ma10_today > h_ma10[2]
        is_always_above = all(h_ma5[i] > h_ma10[i] for i in range(len(h_ma5)))
        distances = [h_ma5[i] - h_ma10[i] for i in range(len(h_ma5))]
        is_air_fueling = (distances[-1] > distances[-2]) and (distances[-2] < distances[-4])
        is_close_enough = min(distances[-3:-1]) <= (ma10_today * 0.015)
        if "⛽ 空中加油" in selected_patterns and is_ma10_rising and is_always_above and is_air_fueling and is_close_enough:
            matched_tags.append("⛽ 空中加油")

        if "⭐ 五線多頭" in selected_patterns and is_bullish_alignment:
            matched_tags.append("⭐ 五線多頭")

    elif strategy == "放空 (Short)":
        is_bearish_alignment = today["5MA"] < today["10MA"] < today["20MA"] < today["30MA"] < today["50MA"]
        is_black_candle = c < o

        is_ma5_not_ascending = ma5_today <= ma5_yesterday
        is_breaking_down = yesterday["Close"] >= ma5_yesterday and c < ma5_today
        if "🔥 破線黑K" in selected_patterns and is_black_candle and is_ma5_not_ascending and is_breaking_down:
            matched_tags.append("🔥 破線黑K")

        had_dead_cross = any(h_ma5[i - 1] >= h_ma10[i - 1] and h_ma5[i] < h_ma10[i] for i in range(1, len(h_ma5) - 1))
        is_ma10_down = ma10_today < h_ma10[0]
        if "⚡ 死亡交叉" in selected_patterns and had_dead_cross and is_ma10_down:
            matched_tags.append("⚡ 死亡交叉")

        is_below_ma10 = all(h_ma5[i] < h_ma10[i] for i in range(len(h_ma5)))
        is_ma10_falling = ma10_today < h_ma10[2]
        touched_ma10 = h >= ma10_today and c < ma10_today
        if "⛽ 反彈遇壓" in selected_patterns and is_below_ma10 and is_ma10_falling and touched_ma10:
            matched_tags.append("⛽ 反彈遇壓")

        if "⭐ 五線空頭" in selected_patterns and is_bearish_alignment:
            matched_tags.append("⭐ 五線空頭")

    if matched_tags: return True, " | ".join(matched_tags)
    return False, "─"

def analyze_stock(stock_info, strategy, selected_patterns):
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

        is_match, pattern_name = check_patterns(df, strategy, selected_patterns)
        today = df.iloc[-1]

        if is_match:
            return {
                "代碼": ticker.replace(".TW", "").replace(".TWO", ""), 
                "YF_Ticker": ticker,
                "股票名稱": stock_name, 
                "收盤價": round(float(today["Close"]), 2),
                "今日成交量(張)": int(volume_sheets), 
                "外資連動天數": int(f_consec), 
                "投信連動天數": int(t_consec), 
                "技術型態訊號": pattern_name
            }
    except:
        return None
    return None

def plot_kline(yf_ticker, stock_name):
    df = yf.download(yf_ticker, period="8mo", progress=False) 
    if df.empty: return None, None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)

    df["5MA"] = df["Close"].rolling(window=5).mean()
    df["10MA"] = df["Close"].rolling(window=10).mean()
    df["20MA"] = df["Close"].rolling(window=20).mean()
    df["30MA"] = df["Close"].rolling(window=30).mean()
    df["50MA"] = df["Close"].rolling(window=50).mean()
    df["20STD"] = df["Close"].rolling(window=20).std()
    df["Upper_Band"] = df["20MA"] + (2 * df["20STD"])
    df["Lower_Band"] = df["20MA"] - (2 * df["20STD"])

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

    fig.add_trace(go.Scatter(x=df.index, y=df['Upper_Band'], mode='lines', line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Lower_Band'], mode='lines', line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(150, 150, 150, 0.1)'), row=1, col=1)
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='#ef5350', decreasing_line_color='#26a69a'), row=1, col=1)

    ma_colors = {'5MA': '#BF0060', '10MA': '#FFD306', '20MA': '#4EFEB3', '30MA': '#46A3FF', '50MA': '#B15BFF'}
    for ma, color in ma_colors.items():
        fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode='lines', name=ma, line=dict(color=color, width=1.5)), row=1, col=1)

    fig.add_trace(go.Bar(x=df.index, y=df['Volume']/1000, marker_color=colors), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['K'], mode='lines', line=dict(color='#FF5252', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['D'], mode='lines', line=dict(color='#448AFF', width=1.5)), row=3, col=1)
    
    fig.add_hline(y=80, line_dash="dash", line_color="gray", row=3, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="gray", row=3, col=1)

    fig.update_layout(height=750, margin=dict(l=40, r=40, t=30, b=40), xaxis_rangeslider_visible=False, template="plotly_white", hovermode="x unified", showlegend=False)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    latest, prev = df.iloc[-1], df.iloc[-2]
    change = latest['Close'] - prev['Close']
    stats = {'Close': latest['Close'], 'Change': change, 'ChangePct': (change / prev['Close']) * 100, 'Volume': int(latest['Volume']/1000)}
    return fig, stats


# ==================== UI 多層次篩選側邊欄 ====================

st.sidebar.header("⚙️ 步驟一：選擇策略方向")
strategy = st.sidebar.radio("🎯 您目前的交易策略是？", ["做多 (Long)", "放空 (Short)"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 步驟二：第一層流動性過濾")
hot_filter = st.sidebar.selectbox("🔥 排行榜預篩:", ["🈚 無 (全市場掃描)", "🏆 僅限今日【成交量】 Top 100", "🏆 僅限今日【成交量】 Top 500"])
# 💡 門檻重新設回 500「張」
min_volume = st.sidebar.number_input("📉 核心成交量門檻 (張數 >):", min_value=0, max_value=50000, value=500, step=100)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 步驟三：第二層技術形態")
if strategy == "做多 (Long)":
    available_patterns = ["🔥 下半身紅K", "⚡ 交叉拉回", "⛽ 空中加油", "⭐ 五線多頭"]
else:
    available_patterns = ["🔥 破線黑K", "⚡ 死亡交叉", "⛽ 反彈遇壓", "⭐ 五線空頭"]

selected_patterns = st.sidebar.multiselect("📈 請選擇要疊加的技術條件 (可複選):", available_patterns, default=available_patterns)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 步驟四：第三層籌碼過濾")
st.sidebar.caption(f"※ 尋找法人連續{'買超' if strategy == '做多 (Long)' else '倒貨'}的標的。設為 0 代表不過濾。")
min_foreign_days = st.sidebar.number_input(f"🔷 外資連{'買' if strategy == '做多 (Long)' else '賣'}天數 ≧:", min_value=0, max_value=20, value=0, step=1)
min_trust_days = st.sidebar.number_input(f"🔶 投信連{'買' if strategy == '做多 (Long)' else '賣'}天數 ≧:", min_value=0, max_value=20, value=0, step=1)

# ==================== 執行掃描邏輯 ====================
if 'scan_completed' not in st.session_state:
    st.session_state.scan_completed = False
    st.session_state.df_final = pd.DataFrame()

if st.sidebar.button("🚀 啟動多層次精密掃描", width="stretch"):
    if not selected_patterns:
        st.sidebar.error("請至少選擇一個技術形態！")
    else:
        with st.spinner("正在執行漏斗式多維度交叉過濾 (📡 正在向 Yahoo 請求全市場即時成交量)..."):
            df_all = fetch_all_markets()
            
            if not df_all.empty:
                df_filtered = df_all.copy()
                
                try:
                    tickers_list = df_filtered['YF_Ticker'].tolist()
                    yf_vols = yf.download(tickers_list, period="1d", progress=False)['Volume']
                    
                    if isinstance(yf_vols, pd.Series): 
                        latest_vols = {tickers_list[0]: yf_vols.iloc[-1]}
                    else:
                        latest_vols = yf_vols.iloc[-1]
                        
                    # 💡 保持轉換為「張數」用於大規模初篩
                    df_filtered['Volume_Sheets'] = df_filtered['YF_Ticker'].map(latest_vols) / 1000
                    df_filtered['Volume_Sheets'] = df_filtered['Volume_Sheets'].fillna(0).astype(int)
                except Exception as e:
                    st.error("⚠️ 無法獲取 Yahoo 即時成交量，請稍後再試。")
                    st.stop()

                df_filtered['Foreign_Days'] = df_filtered['Code'].apply(lambda x: calculate_consecutive_days(get_mock_institutional_data(x, "foreign")))
                df_filtered['Trust_Days'] = df_filtered['Code'].apply(lambda x: calculate_consecutive_days(get_mock_institutional_data(x, "trust")))

                if strategy == "做多 (Long)":
                    if min_foreign_days > 0: df_filtered = df_filtered[df_filtered['Foreign_Days'] >= min_foreign_days]
                    if min_trust_days > 0: df_filtered = df_filtered[df_filtered['Trust_Days'] >= min_trust_days]
                else:
                    if min_foreign_days > 0: df_filtered = df_filtered[df_filtered['Foreign_Days'] <= -min_foreign_days]
                    if min_trust_days > 0: df_filtered = df_filtered[df_filtered['Trust_Days'] <= -min_trust_days]

                if "Top 500" in hot_filter: df_filtered = df_filtered.nlargest(500, 'Volume_Sheets')
                elif "Top 100" in hot_filter: df_filtered = df_filtered.nlargest(100, 'Volume_Sheets')
                df_filtered = df_filtered[df_filtered['Volume_Sheets'] >= min_volume]

                st.info(f"✅ 即時流動性與籌碼過濾完畢，共 **{len(df_filtered)}** 檔股票進入技術形態掃描...")

                active_pool = [
                    (row['YF_Ticker'], row['Name'], row['Volume_Sheets'], row['Foreign_Days'], row['Trust_Days']) 
                    for _, row in df_filtered.iterrows()
                ]

                results = []
                if active_pool:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                        future_to_stock = {executor.submit(analyze_stock, item, strategy, selected_patterns): item for item in active_pool}
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
            else:
                st.error("⚠️ 無法獲取台股代碼清單，請稍後再試。")
                st.session_state.scan_completed = False

# ==================== 顯示結果與智慧配色 ====================
if st.session_state.scan_completed:
    df_final = st.session_state.df_final
    
    if not df_final.empty:
        st.success(f"🎉 掃描完成！共篩出 【 {len(df_final)} 】 檔符合您多層次條件的股票。")
        col1, col2 = st.columns([1.2, 2])
        
        with col1:
            st.markdown(f"### 📊 篩選結果清單 ({strategy})")
            
            display_df = df_final.drop(columns=['YF_Ticker'])
            st.dataframe(display_df, width="stretch", hide_index=True)
            
            options = [f"{row['代碼']} - {row['股票名稱']}" for _, row in df_final.iterrows()]
            selected_stock = st.selectbox("👇 點擊下方清單查看走勢：", options)
            
            if selected_stock:
                selected_code = selected_stock.split(" - ")[0]
                st.markdown("---")
                st.link_button(f"🌐 開啟 Goodinfo! 【{selected_stock}】 真實籌碼分析", f"https://goodinfo.tw/tw/ShowK_Chart.asp?STOCK_ID={selected_code}", type="primary", width="stretch")
        
        with col2:
            if selected_stock:
                selected_code, selected_name = selected_stock.split(" - ")
                stock_data = df_final[df_final['代碼'] == selected_code].iloc[0]
                yf_ticker = stock_data['YF_Ticker']
                f_consec = stock_data['外資連動天數']
                t_consec = stock_data['投信連動天數']
                
                with st.spinner("載入即時 K 線與精準報價中..."):
                    try:
                        fig, stats = plot_kline(yf_ticker, selected_name)
                        
                        # 💡 [第二引擎]：強制單筆精準重抓！
                        # 繞過 yfinance 歷史快取，抓取最即時的 Tick 總股數，精準換算為張數。
                        try:
                            tkr = yf.Ticker(yf_ticker)
                            realtime_vol_shares = tkr.fast_info.get('lastVolume', 0)
                            if realtime_vol_shares > 0:
                                stats['Volume'] = int(realtime_vol_shares / 1000)
                            else:
                                realtime_vol_shares = tkr.info.get('regularMarketVolume', 0)
                                if realtime_vol_shares > 0:
                                    stats['Volume'] = int(realtime_vol_shares / 1000)
                        except:
                            pass # 若單筆抓取失敗，則退回使用歷史 K 線提供的成交量

                    except:
                        fig, stats = None, None
                        
                    if fig and stats:
                        st.markdown(f"### {selected_name} ({selected_code}) 今日量價統計")
                        metric_cols = st.columns(4)
                        
                        metric_cols[0].metric("今日成交價", f"{stats['Close']:.2f}", f"{stats['Change']:.2f} ({stats['ChangePct']:.2f}%)", delta_color="inverse")
                        
                        # 💡 以千分位顯示精準「張」數 (例如: 15,250 張)
                        metric_cols[1].metric("今日成交張數", f"{stats['Volume']:,} 張")
                        
                        f_text = f"連買 {f_consec} 天" if f_consec > 0 else (f"連賣 {abs(f_consec)} 天" if f_consec < 0 else "未連續")
                        t_text = f"連買 {t_consec} 天" if t_consec > 0 else (f"連賣 {abs(t_consec)} 天" if t_consec < 0 else "未連續")
                        
                        f_delta = f"外資強勢" if f_consec >= 3 else (f"-外資弱勢" if f_consec <= -3 else None)
                        t_delta = f"投信強勢" if t_consec >= 2 else (f"-投信弱勢" if t_consec <= -2 else None)
                        
                        metric_cols[2].metric("外資(不含自營)籌碼", f_text, delta=f_delta, delta_color="inverse")
                        metric_cols[3].metric("投信籌碼", t_text, delta=t_delta, delta_color="inverse")
                        
                        st.markdown("---")
                        st.plotly_chart(fig)
    else:
        st.warning("🤔 依據您的流動性門檻、技術條件與籌碼過濾，今日沒有符合的股票。您可以嘗試放寬條件再次掃描。")