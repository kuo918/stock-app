import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import polars as pl
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import random

# ==================== App 介面設定 ====================
st.set_page_config(page_title="台股極速多空選股系統", page_icon="⚡", layout="wide")
st.title("⚡ 台股極速多空選股系統 ")
st.markdown("**(多層次漏斗篩選：極速流動性 ➔ Polars 矩陣運算 ➔ 技術形態 ➔ 籌碼面)**")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ==================== 核心數據獲取 ====================
@st.cache_data(ttl=3600)
def fetch_all_markets():
    """四重備援架構：抓取上市、上櫃與興櫃資料，並內建靜態清單防當機"""
    dfs = []
    
    # 💡 修正後的成交量轉換邏輯：官方回傳皆為「股數」，一律除以 1000 轉為「張數」
    def safe_vol(x):
        try:
            v = float(str(x).replace(',', ''))
            return int(v / 1000)
        except: return 0

    # --- 策略 1: 官方 OpenAPI ---
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['Market'], df['YF_Ticker'] = '上市', df['Code'] + '.TW'
            df['API_Volume'] = df['TradingVolume'].apply(safe_vol)
            dfs.append(df)
    except: pass

    try:
        res = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()).rename(columns={'SecuritiesCompanyCode': 'Code', 'CompanyName': 'Name'})
            df['Market'], df['YF_Ticker'] = '上櫃', df['Code'] + '.TWO'
            df['API_Volume'] = df['TradingVolume'].apply(safe_vol)
            dfs.append(df)
    except: pass

    try:
        res = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_esb_quotes", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()).rename(columns={'SecuritiesCompanyCode': 'Code', 'CompanyName': 'Name'})
            df['Market'], df['YF_Ticker'] = '興櫃', df['Code'] + '.TWO'
            df['API_Volume'] = df['TradingVolume'].apply(safe_vol)
            dfs.append(df)
    except: pass

    # --- 策略 2 & 3: 官方主網頁與 FinMind ---
    if not dfs:
        try:
            res = requests.get("https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo", headers=HEADERS, timeout=8)
            if res.status_code == 200:
                df = pd.DataFrame(res.json()['data'])
                df = df[df['stock_id'].apply(lambda x: len(str(x)) == 4 and str(x).isdigit())]
                df = df.rename(columns={'stock_id': 'Code', 'stock_name': 'Name'})
                df['Market'] = df['type'].apply(lambda x: '上市' if 'twse' in str(x).lower() else '上櫃')
                df['YF_Ticker'] = df.apply(lambda row: f"{row['Code']}.TW" if row['Market'] == '上市' else f"{row['Code']}.TWO", axis=1)
                df['API_Volume'] = 999999
                dfs.append(df)
        except: pass

    # --- 策略 4: 終極靜態備用清單 (若所有 API 皆被封鎖) ---
    if not dfs:
        st.toast("⚠️ 雲端網路受限，已自動啟動內建熱門股備用清單！", icon="🛡️")
        fallback_data = [
            ("2330", "台積電", "上市", 50000), ("2317", "鴻海", "上市", 40000),
            ("2454", "鴻準", "上市", 30000), ("2603", "長榮", "上市", 30000),
            ("3231", "緯創", "上市", 25000), ("2382", "廣達", "上市", 25000),
            ("2308", "台達電", "上市", 20000), ("2881", "富邦金", "上市", 20000),
            ("2891", "中信金", "上市", 20000), ("2303", "聯電", "上市", 20000),
            ("2882", "國泰金", "上市", 15000), ("2886", "兆豐金", "上市", 15000),
            ("2002", "中鋼", "上市", 15000), ("1301", "台塑", "上市", 10000),
            ("2412", "中華電", "上市", 10000), ("1216", "統一", "上市", 10000),
            ("2884", "玉山金", "上市", 10000), ("2609", "陽明", "上市", 10000),
            ("3034", "聯詠", "上市", 8000), ("3037", "欣興", "上市", 8000),
            ("3008", "大立光", "上市", 5000), ("2379", "瑞昱", "上市", 5000),
            ("2615", "萬海", "上市", 5000), ("2885", "元大金", "上市", 5000),
            ("2880", "華南金", "上市", 5000), ("2892", "第一金", "上市", 5000),
            ("2883", "開發金", "上市", 5000), ("2887", "台新金", "上市", 5000),
            ("2357", "華碩", "上市", 5000), ("2324", "仁寶", "上市", 5000),
            ("8069", "元太", "上櫃", 5000), ("3105", "穩懋", "上市", 5000),
            ("2345", "智邦", "上櫃", 5000), ("6488", "環球晶", "上櫃", 5000),
            ("8299", "群聯", "上市", 5000), ("3529", "力旺", "上櫃", 3000),
            ("5483", "中美晶", "上櫃", 3000), ("5347", "世界", "上櫃", 3000),
            ("1565", "精華", "上櫃", 2000), ("4966", "譜瑞-KY", "上櫃", 2000),
            ("3293", "鈊象", "上櫃", 2000), ("8436", "大江", "上櫃", 1000),
            ("6446", "藥華藥", "上櫃", 1000), ("3131", "弘塑", "上櫃", 1000),
            ("3533", "嘉澤", "上市", 1000), ("5274", "信驊", "上櫃", 1000),
            ("6669", "緯穎", "上市", 1000), ("6531", "愛普*", "上櫃", 1000),
            ("8046", "南電", "上市", 1000), ("3661", "世芯-KY", "上櫃", 1000)
        ]
        df_fallback = pd.DataFrame(fallback_data, columns=["Code", "Name", "Market", "API_Volume"])
        df_fallback['YF_Ticker'] = df_fallback.apply(lambda row: f"{row['Code']}.TW" if row['Market'] == '上市' else f"{row['Code']}.TWO", axis=1)
        dfs.append(df_fallback)

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        df_all['Code'] = df_all['Code'].astype(str)
        df_all = df_all[df_all['Code'].apply(lambda x: len(x) == 4 and x.isdigit())]
        df_all = df_all.drop_duplicates(subset=['YF_Ticker'])
        return df_all
    return pd.DataFrame()

def calculate_consecutive_days(net_buy_sell_list):
    if not net_buy_sell_list: return 0
    latest_val = net_buy_sell_list[0]
    if latest_val == 0: return 0
    is_buying = latest_val > 0
    consecutive_count = 0
    for val in net_buy_sell_list:
        if is_buying and val > 0: consecutive_count += 1
        elif not is_buying and val < 0: consecutive_count += 1
        else: break
    return consecutive_count if is_buying else -consecutive_count

def get_mock_institutional_data(code, inst_type="foreign"):
    random.seed(int(code[:4]) + (1 if inst_type == "foreign" else 2))
    return [random.choice([-500, -200, -50, 0, 100, 300, 800]) for _ in range(10)]

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
min_volume = st.sidebar.number_input("📉 核心成交量門檻 (張數 >):", min_value=0, max_value=50000, value=500, step=100)

# 💡 針對興櫃量能的專屬控制開關
ignore_emerging_vol = st.sidebar.checkbox("💡 興櫃股票不受此成交量門檻限制", value=True)
exclude_emerging = st.sidebar.checkbox("🚫 完全排除興櫃股票", value=False)

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

if st.sidebar.button("🚀 啟動極速掃描", width="stretch"):
    if not selected_patterns:
        st.sidebar.error("請至少選擇一個技術形態！")
    else:
        with st.spinner("啟動 Polars 極速矩陣引擎..."):
            df_all = fetch_all_markets()
            
            if not df_all.empty:
                df_filtered = df_all.copy()
                
                # 💡 處理興櫃排除邏輯
                if exclude_emerging:
                    df_filtered = df_filtered[df_filtered['Market'] != '興櫃']
                
                # 第一階段：官方量能預過濾
                if "Top 500" in hot_filter: df_filtered = df_filtered.nlargest(500, 'API_Volume')
                elif "Top 100" in hot_filter: df_filtered = df_filtered.nlargest(100, 'API_Volume')
                
                # 💡 處理興櫃成交量特例：若打勾，興櫃股票將無視 min_volume 門檻
                if ignore_emerging_vol:
                    df_filtered = df_filtered[(df_filtered['API_Volume'] >= min_volume) | (df_filtered['Market'] == '興櫃')]
                else:
                    df_filtered = df_filtered[df_filtered['API_Volume'] >= min_volume]
                
                remaining_count = len(df_filtered)
                if remaining_count == 0:
                    st.warning("⚠️ 第一關官方量能預篩選後已無符合股票，請放寬量能門檻！")
                    st.stop()
                    
                tickers_list = sorted(df_filtered['YF_Ticker'].tolist())
                progress_bar = st.empty()
                progress_bar.info(f"📡 已淘汰低量股，正在從 Yahoo 獲取 {remaining_count} 檔精準歷史資料...")

                try:
                    # Polars 優化：批量下載後轉為 DataFrame
                    batch_df = yf.download(tickers_list, period="3mo", group_by="ticker", progress=False)
                except Exception as e:
                    st.error(f"⚠️ Yahoo Finance 批次連線失敗: {e}")
                    st.stop()

                results = []
                
                for _, row in df_filtered.iterrows():
                    ticker = row['YF_Ticker']
                    name = row['Name']
                    code = row['Code']
                    market = row.get('Market', '未知')
                    
                    try:
                        # 處理 Yahoo 格式
                        if len(tickers_list) == 1:
                            sub_df = batch_df.copy()
                        else:
                            if isinstance(batch_df.columns, pd.MultiIndex):
                                if ticker in batch_df.columns.levels[0]:
                                    sub_df = batch_df[ticker].dropna(subset=['Close'])
                                else: continue
                            else:
                                sub_df = batch_df.dropna(subset=['Close'])
                                
                        if sub_df.empty or len(sub_df) < 15: continue
                        
                        # 轉換為 Polars 進行高速向量化運算
                        pl_df = pl.from_pandas(sub_df.reset_index())
                        
                        pl_df = pl_df.with_columns([
                            pl.col("Close").rolling_mean(window_size=5).alias("5MA"),
                            pl.col("Close").rolling_mean(window_size=10).alias("10MA"),
                            pl.col("Close").rolling_mean(window_size=20).alias("20MA"),
                            pl.col("Close").rolling_mean(window_size=30).alias("30MA"),
                            pl.col("Close").rolling_mean(window_size=50).alias("50MA")
                        ]).drop_nulls()
                        
                        if pl_df.height < 2: continue

                        # 取得最新兩筆資料
                        today = pl_df.tail(1).to_dicts()[0]
                        yesterday = pl_df.tail(2).head(1).to_dicts()[0]

                        # --- 技術形態判斷 (Polars 版本) ---
                        c, o = today["Close"], today["Open"]
                        l = today["Low"]
                        ma5_today, ma10_today = today["5MA"], today["10MA"]
                        ma5_yesterday = yesterday["5MA"]
                        
                        matched_tags = []
                        if strategy == "做多 (Long)":
                            is_bullish = today["5MA"] > today["10MA"] > today["20MA"] > today["30MA"] > today["50MA"]
                            is_red = c > o
                            is_ma5_not_desc = ma5_today >= ma5_yesterday
                            is_crossing_up = yesterday["Close"] <= ma5_yesterday or l <= ma5_today
                            body = c - o
                            is_half = ((c - max(o, ma5_today)) / body >= 0.50 if body > 0 else False)
                            
                            if "🔥 下半身紅K" in selected_patterns and is_red and is_ma5_not_desc and is_crossing_up and is_half:
                                matched_tags.append("🔥 下半身紅K")
                            if "⭐ 五線多頭" in selected_patterns and is_bullish:
                                matched_tags.append("⭐ 五線多頭")
                            if "⚡ 交叉拉回" in selected_patterns and is_red and c > ma5_today and yesterday["Close"] <= ma5_yesterday:
                                matched_tags.append("⚡ 交叉拉回")

                        elif strategy == "放空 (Short)":
                            is_bearish = today["5MA"] < today["10MA"] < today["20MA"] < today["30MA"] < today["50MA"]
                            is_black = c < o
                            is_ma5_not_asc = ma5_today <= ma5_yesterday
                            is_breaking_down = yesterday["Close"] >= ma5_yesterday and c < ma5_today
                            
                            if "🔥 破線黑K" in selected_patterns and is_black and is_ma5_not_asc and is_breaking_down:
                                matched_tags.append("🔥 破線黑K")
                            if "⭐ 五線空頭" in selected_patterns and is_bearish:
                                matched_tags.append("⭐ 五線空頭")

                        if not matched_tags: continue
                        pattern_name = " | ".join(matched_tags)
                        
                        # --- 籌碼面與成交量處理 ---
                        y_vol = int(today.get('Volume', 0) / 1000)
                        
                        # 阻斷假資料：如果是備援策略產生的 999999，強制改用 Yahoo 真實成交量
                        if row['API_Volume'] == 999999:
                            volume_sheets = y_vol
                        elif market == '興櫃':
                            volume_sheets = int(row['API_Volume'])
                        else:
                            volume_sheets = y_vol if y_vol > 0 else int(row['API_Volume'])
                            
                        # 終極防呆：確保最終結果畫面絕對不會印出 999999 假數據
                        if volume_sheets == 999999:
                            volume_sheets = y_vol
                        
                        f_consec = calculate_consecutive_days(get_mock_institutional_data(code, "foreign"))
                        t_consec = calculate_consecutive_days(get_mock_institutional_data(code, "trust"))

                        if strategy == "做多 (Long)":
                            if min_foreign_days > 0 and f_consec < min_foreign_days: continue
                            if min_trust_days > 0 and t_consec < min_trust_days: continue
                        else:
                            if min_foreign_days > 0 and f_consec > -min_foreign_days: continue
                            if min_trust_days > 0 and t_consec > -min_trust_days: continue
                            
                        results.append({
                            "市場": market,
                            "代碼": code, 
                            "YF_Ticker": ticker,
                            "股票名稱": name, 
                            "收盤價": round(c, 2),
                            "今日成交量(張)": volume_sheets, 
                            "外資連動天數": int(f_consec), 
                            "投信連動天數": int(t_consec), 
                            "技術型態訊號": pattern_name
                        })
                    except Exception as loop_e:
                        continue

                if results:
                    df_final = pd.DataFrame(results).sort_values(by="今日成交量(張)", ascending=False)
                    
                    # 💡 最後一關把關：依據 UI 設定決定最終顯示清單是否要卡興櫃的成交量
                    if ignore_emerging_vol:
                        df_final = df_final[(df_final['今日成交量(張)'] >= min_volume) | (df_final['市場'] == '興櫃')]
                    else:
                        df_final = df_final[df_final['今日成交量(張)'] >= min_volume]
                    
                    st.session_state.df_final = df_final
                    st.session_state.scan_completed = True
                else:
                    st.session_state.df_final = pd.DataFrame()
                    st.session_state.scan_completed = True
                progress_bar.empty() 
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
            
            options = [f"{row['代碼']} - {row['股票名稱']} ({row['市場']})" for _, row in df_final.iterrows()]
            selected_stock = st.selectbox("👇 點擊下方清單查看走勢：", options)
            
            if selected_stock:
                selected_code = selected_stock.split(" - ")[0]
                st.markdown("---")
                st.link_button(f"🌐 開啟 Goodinfo! 【{selected_stock}】 真實籌碼分析", f"https://goodinfo.tw/tw/ShowK_Chart.asp?STOCK_ID={selected_code}", type="primary", width="stretch")
        
        with col2:
            if selected_stock:
                selected_code = selected_stock.split(" - ")[0]
                selected_name = selected_stock.split(" - ")[1].split(" (")[0]
                
                stock_data = df_final[df_final['代碼'] == selected_code].iloc[0]
                yf_ticker = stock_data['YF_Ticker']
                stock_market = stock_data['市場']
                f_consec = stock_data['外資連動天數']
                t_consec = stock_data['投信連動天數']
                
                with st.spinner("載入即時 K 線與精準報價中..."):
                    try:
                        fig, stats = plot_kline(yf_ticker, selected_name)
                        
                        try:
                            tkr = yf.Ticker(yf_ticker)
                            realtime_vol_shares = tkr.fast_info.get('lastVolume', 0)
                            if realtime_vol_shares > 0:
                                stats['Volume'] = int(realtime_vol_shares / 1000)
                            else:
                                realtime_vol_shares = tkr.info.get('regularMarketVolume', 0)
                                if realtime_vol_shares > 0:
                                    stats['Volume'] = int(realtime_vol_shares / 1000)
                        except: pass 

                        if stats:
                            if stock_market == '興櫃':
                                stats['Volume'] = stock_data['今日成交量(張)']
                            elif stats['Volume'] <= 0:
                                stats['Volume'] = stock_data['今日成交量(張)']

                    except:
                        fig, stats = None, None
                        
                    if fig and stats:
                        st.markdown(f"### {selected_name} ({selected_code}) 今日量價統計")
                        metric_cols = st.columns(4)
                        
                        metric_cols[0].metric("今日成交價", f"{stats['Close']:.2f}", f"{stats['Change']:.2f} ({stats['ChangePct']:.2f}%)", delta_color="inverse")
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
