import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台灣基金滾動10日跌幅系統", layout="wide")
st.title("📉 台灣基金滾動10日跌幅系統")
st.caption("資料來源：MoneyDJ清單 + Yahoo Finance歷史淨值 | 更新時間：" + datetime.now().strftime("%Y-%m-%d %H:%M"))

HEADERS_YAHOO = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
HEADERS_MDJ = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.moneydj.com/funddj/",
}
HORIZONS = [10, 20, 50, 100, 200]
THRESHOLDS = [-5, -7, -10, -15, -20]

DOMESTIC_COMPANIES = {
    "安聯投信": "BFZ002", "兆豐投信": "BFZ014", "元大投信": "BFZIIA",
    "國泰投信": "BFZGCA", "富邦投信": "BFZFPA", "群益投信": "BFZCYA",
    "中國信託投信": "BFZCAA", "凱基投信": "BFZCIA", "台新投信": "BFZTIA",
    "統一投信": "BFZUNA", "復華投信": "BFZFHA", "第一金投信": "BFZNCA",
    "永豐投信": "BFZYTA", "野村投信": "BFZ004", "摩根投信": "BFZPSA",
    "瀚亞投信": "BFZAIA", "聯博投信": "BFZAPA", "柏瑞投信": "BFZBRA",
    "施羅德投信": "BFZCSA", "景順投信": "BFZICA", "宏利投信": "BFZ008",
    "華南永昌投信": "BFZ007", "新光投信": "BFZ010", "合庫投信": "BFZ012",
    "台灣投信": "BFZDFA", "全部境內基金": "ALL_DOM",
}


# ==============================
# Step1: MoneyDJ抓基金清單
# ==============================
@st.cache_data(ttl=86400)
def get_moneydj_fund_list(company_code):
    """從MoneyDJ抓基金清單，回傳 list of {mdj_code, name}"""
    funds = []
    if company_code == "ALL_DOM":
        url = "https://www.moneydj.com/funddj/ya/yp082000.djhtm"
    elif company_code == "OFFSHORE":
        url = "https://www.moneydj.com/funddj/ya/yp081001.djhtm"
    else:
        url = "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=" + company_code
    try:
        res = requests.get(url, headers=HEADERS_MDJ, timeout=15, verify=False)
        res.encoding = "big5"
        soup = BeautifulSoup(res.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "yp010000" in href or "yp010001" in href:
                match = re.search(r"a=([A-Za-z0-9]+)", href)
                if match:
                    code = match.group(1)
                    name = a.get_text(strip=True)
                    if name and len(name) > 2:
                        funds.append({"mdj_code": code, "name": name})
    except:
        pass
    # 去重
    seen = set()
    unique = []
    for f in funds:
        if f["mdj_code"] not in seen:
            seen.add(f["mdj_code"])
            unique.append(f)
    return unique


# ==============================
# Step2: 用基金名稱搜尋Yahoo代碼
# ==============================
@st.cache_data(ttl=86400)
def get_yahoo_code(fund_name):
    """用基金名稱搜尋Yahoo Finance，取得Yahoo代碼"""
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {
        "q": fund_name[:20],  # 取前20字避免太長
        "lang": "zh-TW",
        "region": "TW",
        "quotesCount": 5,
        "newsCount": 0,
    }
    try:
        res = requests.get(url, headers=HEADERS_YAHOO, params=params, timeout=8)
        data = res.json()
        for q in data.get("quotes", []):
            sym = q.get("symbol", "")
            qtype = q.get("quoteType", "")
            if (":FO" in sym or qtype == "MUTUALFUND") and sym:
                return sym
    except:
        pass
    return None


# ==============================
# Step3: Yahoo Finance抓歷史淨值
# ==============================
def get_nav_history(yahoo_code, days=365*15+30):
    end = datetime.today()
    start = end - timedelta(days=days)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/" + yahoo_code
        + "?interval=1d&period1=" + str(int(start.timestamp()))
        + "&period2=" + str(int(end.timestamp()))
    )
    try:
        res = requests.get(url, headers=HEADERS_YAHOO, timeout=15)
        data = res.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        prices = {}
        for ts, cl in zip(timestamps, closes):
            if cl is not None:
                date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                prices[date] = round(cl, 4)
        return prices
    except:
        return {}


def get_nav_recent(yahoo_code):
    return get_nav_history(yahoo_code, days=60)


# ==============================
# 建立基金代碼對照表（MDJ → Yahoo）
# ==============================
@st.cache_data(ttl=86400)
def build_fund_map(company_code):
    """建立完整的基金對照表"""
    mdj_funds = get_moneydj_fund_list(company_code)
    result = []
    for f in mdj_funds:
        yahoo_code = get_yahoo_code(f["name"])
        result.append({
            "名稱": f["name"],
            "MDJ代碼": f["mdj_code"],
            "Yahoo代碼": yahoo_code or "未找到",
        })
        time.sleep(0.3)
    return result


# ==============================
# 計算函數
# ==============================
def calc_rolling_latest(prices_dict, threshold):
    if len(prices_dict) < 11:
        return None, None, 0
    dates = sorted(prices_dict.keys())
    latest = prices_dict[dates[-1]]
    base = prices_dict[dates[-11]]
    if base == 0:
        return None, None, 0
    ret = (latest - base) / base * 100
    consec = 0
    for i in range(len(dates) - 1, 9, -1):
        b = prices_dict[dates[i - 10]]
        c = prices_dict[dates[i]]
        if b > 0 and (c - b) / b * 100 <= threshold:
            consec += 1
        else:
            break
    return ret, latest, consec


def calc_all_rolling(prices_dict):
    if len(prices_dict) < 11:
        return []
    dates = sorted(prices_dict.keys())
    results = []
    for i in range(10, len(dates)):
        bp = prices_dict[dates[i - 10]]
        cp = prices_dict[dates[i]]
        if bp > 0:
            ret = (cp - bp) / bp * 100
            results.append({
                "date": dates[i], "base_date": dates[i - 10],
                "base_price": bp, "curr_price": cp, "return": round(ret, 2)
            })
    return results


def run_backtest(prices_dict, threshold):
    rolling = calc_all_rolling(prices_dict)
    if not rolling:
        return None
    dates = sorted(prices_dict.keys())
    date_to_idx = {d: i for i, d in enumerate(dates)}
    triggers = [r for r in rolling if r["return"] <= threshold]
    if not triggers:
        return None

    trigger_dates = set(t["date"] for t in triggers)
    max_consec = cc = 0
    for r in rolling:
        if r["date"] in trigger_dates:
            cc += 1
            max_consec = max(max_consec, cc)
        else:
            cc = 0

    horizon_rets = {h: [] for h in HORIZONS}
    horizon_dds = {h: [] for h in HORIZONS}

    for t in triggers:
        idx = date_to_idx.get(t["date"])
        if idx is None:
            continue
        ep = t["curr_price"]
        year = t["date"][:4]
        for h in HORIZONS:
            fi = idx + h
            if fi < len(dates):
                fp = prices_dict[dates[fi]]
                ret = (fp - ep) / ep * 100
                horizon_rets[h].append({"ret": round(ret, 2), "year": year})
                min_ret = 0.0
                for d in range(1, h + 1):
                    if idx + d < len(dates):
                        p = prices_dict[dates[idx + d]]
                        r = (p - ep) / ep * 100
                        if r < min_ret:
                            min_ret = r
                horizon_dds[h].append({"dd": round(min_ret, 2), "year": year})

    yearly = {}
    for t in triggers:
        year = t["date"][:4]
        if year not in yearly:
            yearly[year] = {"trigger_dates": set(), "max_consec": 0,
                            "rets": {h: [] for h in HORIZONS},
                            "dds": {h: [] for h in HORIZONS}}
        yearly[year]["trigger_dates"].add(t["date"])

    for h in HORIZONS:
        for item in horizon_rets[h]:
            y = item["year"]
            if y in yearly:
                yearly[y]["rets"][h].append(item["ret"])
        for item in horizon_dds[h]:
            y = item["year"]
            if y in yearly:
                yearly[y]["dds"][h].append(item["dd"])

    for year in yearly:
        mc = cc2 = 0
        for r in rolling:
            if r["date"][:4] == year and r["date"] in yearly[year]["trigger_dates"]:
                cc2 += 1
                mc = max(mc, cc2)
            elif r["date"][:4] == year:
                cc2 = 0
        yearly[year]["max_consec"] = mc

    return {
        "triggers": triggers, "trigger_dates": list(trigger_dates),
        "max_consec": max_consec, "horizon_rets": horizon_rets,
        "horizon_dds": horizon_dds, "yearly": yearly, "total": len(triggers)
    }


# ==============================
# 顏色與樣式
# ==============================
def color_ret(val):
    if str(val) in ["", "---", "待觀察", "未找到"]:
        return ""
    try:
        v = float(str(val).replace("%", ""))
        return "color: red; font-weight: bold" if v > 0 else "color: green; font-weight: bold"
    except:
        return ""


def color_dd(val):
    if str(val) in ["", "---", "待觀察"]:
        return ""
    try:
        v = float(str(val).replace("%", ""))
        return "color: green; font-weight: bold" if v < 0 else ""
    except:
        return ""


def color_winrate(val):
    if str(val) in ["", "---", "待觀察"]:
        return ""
    try:
        v = float(str(val).replace("%", ""))
        if v >= 80:
            return "background-color: #FF8C00; color: white; font-weight: bold"
        return ""
    except:
        return ""


def heatmap_ret(df, cols):
    all_vals = []
    for c in cols:
        for v in df[c]:
            try:
                all_vals.append(float(str(v).replace("%", "")))
            except:
                pass
    max_pos = max((v for v in all_vals if v > 0), default=1)
    min_neg = min((v for v in all_vals if v < 0), default=-1)

    def cell(val):
        if str(val) in ["", "---", "待觀察"]:
            return ""
        try:
            v = float(str(val).replace("%", ""))
            if v > 0:
                intensity = min(v / max_pos, 1.0)
                r = int(255 - intensity * 115)
                g = int(224 - intensity * 224)
                b = int(224 - intensity * 224)
                text = "white" if intensity > 0.55 else "#8B0000"
                return "background-color: rgb({},{},{}); color: {}; font-weight: bold".format(r, g, b, text)
            elif v < 0:
                intensity = min(abs(v) / abs(min_neg), 1.0)
                r = int(224 - intensity * 224)
                g = int(255 - intensity * 111)
                b = int(224 - intensity * 224)
                text = "white" if intensity > 0.55 else "#006400"
                return "background-color: rgb({},{},{}); color: {}; font-weight: bold".format(r, g, b, text)
            return ""
        except:
            return ""
    return df.style.map(cell, subset=cols)


def fmt(v):
    return "待觀察" if v is None else "{:.2f}%".format(v)


def show_html(s):
    st.markdown(s.to_html(index=False), unsafe_allow_html=True)


# ==============================
# TABS
# ==============================
tab0, tab1, tab2, tab3 = st.tabs([
    "🔍 每日警示掃描",
    "📊 個基金回測",
    "📖 使用說明",
    "🔧 系統檢核",
])

# ==============================
# TAB 0: 每日警示掃描
# ==============================
with tab0:
    st.subheader("每日警示掃描")
    st.caption("選擇投信公司範圍，系統自動取得基金清單並掃描滾動10日跌幅")

    col1, col2 = st.columns([2, 1])
    with col1:
        company_sel = st.selectbox("選擇投信公司", list(DOMESTIC_COMPANIES.keys()), key="company_sel")
        offshore_toggle = st.checkbox("也包含境外基金", key="offshore_toggle")
    with col2:
        threshold_scan = st.slider("警示門檻（跌幅%）", min_value=-30, max_value=-3, value=-10, step=1, key="thr_scan")

    if st.button("🔍 開始掃描", type="primary", key="scan"):
        company_code = DOMESTIC_COMPANIES[company_sel]
        with st.spinner("取得基金清單中..."):
            dom_funds = get_moneydj_fund_list(company_code)
            all_funds = list(dom_funds)
            if offshore_toggle:
                off_funds = get_moneydj_fund_list("OFFSHORE")
                all_funds += off_funds

        total = len(all_funds)
        if total == 0:
            st.error("無法取得基金清單，請稍後再試")
        else:
            st.info("共 " + str(total) + " 檔，開始掃描（先取得Yahoo代碼再抓淨值）...")
            results = []
            progress = st.progress(0)
            status = st.empty()

            for i, fund in enumerate(all_funds):
                name = fund["name"]
                status.text("掃描：" + name[:20] + "（" + str(i+1) + "/" + str(total) + "）")

                yahoo_code = get_yahoo_code(name)
                if not yahoo_code:
                    progress.progress((i + 1) / total)
                    time.sleep(0.2)
                    continue

                prices = get_nav_recent(yahoo_code)
                ret, latest, consec = calc_rolling_latest(prices, threshold_scan)
                if ret is not None and ret <= threshold_scan:
                    results.append({
                        "基金名稱": name,
                        "Yahoo代碼": yahoo_code,
                        "最新淨值": latest,
                        "滾動10日報酬率": "{:.2f}%".format(ret),
                        "連續觸發天數": consec,
                        "數值": ret
                    })
                progress.progress((i + 1) / total)
                time.sleep(0.3)

            progress.empty()
            status.empty()

            if results:
                df_scan = pd.DataFrame(results).sort_values("數值").drop(columns=["數值"])
                st.error("⚠️ 共 " + str(len(results)) + " 檔觸發（門檻：" + str(threshold_scan) + "%）")
                show_html(df_scan)
                st.download_button("📥 下載CSV", df_scan.to_csv(index=False).encode("utf-8-sig"), "fund_alert.csv", "text/csv")
            else:
                st.success("✅ 目前無基金觸發 " + str(threshold_scan) + "% 警示")

# ==============================
# TAB 1: 個基金回測
# ==============================
with tab1:
    st.subheader("個基金回測（最長15年）")

    st.markdown("#### 搜尋基金")
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        search_kw = st.text_input("輸入基金名稱關鍵字", placeholder="例：安聯收益成長 或 元大台灣50", key="search_kw")
    with col_s2:
        st.write("")
        st.write("")
        do_search = st.button("🔎 搜尋", key="do_search")

    if do_search and search_kw.strip():
        with st.spinner("搜尋中..."):
            yahoo_code_found = get_yahoo_code(search_kw.strip())
        if yahoo_code_found:
            st.success("找到代碼：" + yahoo_code_found)
            st.info("複製下方代碼到「輸入Yahoo代碼」欄位")
            st.code(yahoo_code_found)
        else:
            st.warning("找不到，請試試更精確的名稱（英文名稱有時效果更好）")

    st.divider()
    st.markdown("#### 回測分析")
    col_b1, col_b2 = st.columns([2, 1])
    with col_b1:
        fund_code = st.text_input("輸入Yahoo基金代碼", value="F00000VHRD:FO",
                                   help="格式：F00000XXXX:FO", key="bt_code")
    with col_b2:
        thr_bt = st.selectbox("觸發門檻", [str(t) + "%" for t in THRESHOLDS], index=2, key="thr_bt")

    if st.button("🔬 開始分析", type="primary", key="bt_start"):
        with st.spinner("抓取歷史淨值（最長15年）..."):
            prices = get_nav_history(fund_code)

        if not prices or len(prices) < 11:
            st.error("資料不足，請確認代碼正確（格式：F00000XXXX:FO）")
        else:
            dates_list = sorted(prices.keys())
            st.success("成功抓取 " + str(len(prices)) + " 個交易日（" +
                       dates_list[0] + " ~ " + dates_list[-1] + "）")

            thr_val = int(thr_bt.replace("%", ""))

            # 建所有門檻總覽表
            win_rows, avg_rows, dd_rows = [], [], []
            for thr in THRESHOLDS:
                result = run_backtest(prices, thr)
                wr = {"觸發門檻": str(thr) + "%", "樣本數": 0 if result is None else result["total"]}
                ar = {"觸發門檻": str(thr) + "%", "樣本數": 0 if result is None else result["total"]}
                dr = {"觸發門檻": str(thr) + "%", "樣本數": 0 if result is None else result["total"]}
                for h in HORIZONS:
                    cw = str(h) + "天勝率"
                    ca = str(h) + "天平均報酬%"
                    cd = str(h) + "天平均最大回撤%"
                    if result is None:
                        wr[cw] = ar[ca] = dr[cd] = "---"
                    else:
                        rets = [x["ret"] for x in result["horizon_rets"][h]]
                        dds = [x["dd"] for x in result["horizon_dds"][h]]
                        if not rets:
                            wr[cw] = ar[ca] = dr[cd] = "待觀察"
                        else:
                            wins = sum(1 for r in rets if r > 0)
                            wr[cw] = "{:.2f}%".format(wins / len(rets) * 100)
                            ar[ca] = "{:.2f}%".format(sum(rets) / len(rets))
                            dr[cd] = "{:.2f}%".format(sum(dds) / len(dds))
                win_rows.append(wr)
                avg_rows.append(ar)
                dd_rows.append(dr)

            df_win = pd.DataFrame(win_rows)
            df_avg = pd.DataFrame(avg_rows)
            df_dd = pd.DataFrame(dd_rows)
            win_cols = [str(h) + "天勝率" for h in HORIZONS]
            avg_cols = [str(h) + "天平均報酬%" for h in HORIZONS]
            dd_cols = [str(h) + "天平均最大回撤%" for h in HORIZONS]

            st.markdown("### 表A：勝率（各門檻 × 觀察天數）｜橘色 ≥ 80%")
            show_html(df_win.style.map(color_winrate, subset=win_cols))

            st.markdown("### 表B：平均單次報酬%（各門檻 × 觀察天數）")
            show_html(heatmap_ret(df_avg, avg_cols))

            st.markdown("### 表E：平均最大回撤%（各門檻 × 觀察天數）")
            show_html(df_dd.style.map(color_dd, subset=dd_cols))

            # 年度明細
            result_thr = run_backtest(prices, thr_val)
            if result_thr:
                st.markdown("### 年度明細（門檻 " + thr_bt + "）")
                st.caption("橫向看哪個持有天數報酬最穩；縱向看哪幾年觸發後反彈最強")
                yr_rows = []
                for year in sorted(result_thr["yearly"].keys()):
                    y = result_thr["yearly"][year]
                    row = {"年度": year, "觸發次數": len(y["trigger_dates"]),
                           "最長連續觸發": y["max_consec"]}
                    for h in HORIZONS:
                        rets = y["rets"][h]
                        row[str(h) + "天平均%"] = fmt(round(sum(rets)/len(rets), 2) if rets else None)
                    yr_rows.append(row)
                total_r = {"年度": "合計/平均", "觸發次數": result_thr["total"],
                           "最長連續觸發": result_thr["max_consec"]}
                for h in HORIZONS:
                    rets = [x["ret"] for x in result_thr["horizon_rets"][h]]
                    total_r[str(h) + "天平均%"] = fmt(round(sum(rets)/len(rets), 2) if rets else None)
                yr_rows.append(total_r)
                df_yr = pd.DataFrame(yr_rows)
                yr_cols = [str(h) + "天平均%" for h in HORIZONS]
                show_html(heatmap_ret(df_yr, yr_cols))

                # 表D 進場時機
                st.markdown("### 表D：進場時機比較（門檻 " + thr_bt + "）")
                h_timing = st.selectbox("選擇觀察天數", [str(h) + "天" for h in HORIZONS],
                                         index=2, key="timing_h")
                h_val = int(h_timing.replace("天", ""))
                rolling_all = calc_all_rolling(prices)
                trigger_date_set = set(t["date"] for t in result_thr["triggers"])
                dates_all = sorted(prices.keys())
                date_to_idx = {d: i for i, d in enumerate(dates_all)}
                consec_day = {}
                cc = 0
                for r in rolling_all:
                    if r["date"] in trigger_date_set:
                        cc += 1
                        consec_day[r["date"]] = cc
                    else:
                        cc = 0
                groups = {"連續第1天進場": [], "連續第2天進場": [],
                          "連續第3天以後進場": [], "連續結束翌日進場": []}
                rl = list(rolling_all)
                for i, r in enumerate(rl):
                    d = r["date"]
                    if d not in trigger_date_set:
                        if i > 0 and rl[i-1]["date"] in trigger_date_set:
                            idx = date_to_idx.get(d)
                            if idx is None:
                                continue
                            fi = idx + h_val
                            ret_v = round((prices[dates_all[fi]] - r["curr_price"]) / r["curr_price"] * 100, 2) if fi < len(dates_all) else None
                            groups["連續結束翌日進場"].append(ret_v)
                    else:
                        dn = consec_day.get(d, 1)
                        idx = date_to_idx.get(d)
                        if idx is None:
                            continue
                        fi = idx + h_val
                        ret_v = round((prices[dates_all[fi]] - r["curr_price"]) / r["curr_price"] * 100, 2) if fi < len(dates_all) else None
                        if dn == 1:
                            groups["連續第1天進場"].append(ret_v)
                        elif dn == 2:
                            groups["連續第2天進場"].append(ret_v)
                        else:
                            groups["連續第3天以後進場"].append(ret_v)
                timing_rows = []
                for gname, rets_raw in groups.items():
                    rets = [r for r in rets_raw if r is not None]
                    row = {"進場時機": gname, "樣本數": len(rets_raw)}
                    if not rets:
                        row["勝率"] = "---"
                        row["平均報酬%"] = "---"
                        row["累積報酬%"] = "---"
                    else:
                        wins = sum(1 for r in rets if r > 0)
                        row["勝率"] = "{:.2f}%".format(wins / len(rets) * 100)
                        row["平均報酬%"] = "{:.2f}%".format(sum(rets) / len(rets))
                        row["累積報酬%"] = "{:.2f}%".format(sum(rets))
                    timing_rows.append(row)
                df_t = pd.DataFrame(timing_rows)
                styled_t = heatmap_ret(df_t, ["平均報酬%", "累積報酬%"])
                styled_t = styled_t.map(color_winrate, subset=["勝率"])
                show_html(styled_t)
                st.caption("連續第1天：首次觸發｜連續第2天：跌2天才進｜連續第3天以後：等更深跌｜連續結束翌日：止跌確認後才進")

# ==============================
# TAB 2: 使用說明
# ==============================
with tab2:
    st.markdown("## 使用說明")
    st.info("資料來源：MoneyDJ基金清單 + Yahoo Finance歷史淨值 | 境內各投信公司 + 境外基金")
    st.divider()
    st.markdown("### 使用流程")
    st.markdown("""
**每日警示掃描**
1. 選擇投信公司（或勾選包含境外基金）
2. 設定觸發門檻（預設 -10%）
3. 按「開始掃描」，系統自動：
   - 從MoneyDJ取得該公司的基金清單
   - 用Yahoo Finance搜尋API取得每檔基金的Yahoo代碼
   - 抓取最近60天淨值計算滾動10日跌幅
   - 顯示觸發的基金、最新淨值、連續觸發天數

**個基金回測**
1. 輸入基金名稱關鍵字搜尋，取得Yahoo代碼
2. 貼上Yahoo代碼，選擇觸發門檻
3. 查看15年回測結果：勝率、平均報酬、最大回撤、年度明細、進場時機
    """)
    st.divider()
    st.markdown("### 顏色說明（台灣慣例）")
    st.markdown("""
- 🔴 紅色文字 = 正數（獲利）
- 🟢 綠色文字 = 負數（虧損）
- 🟠 橘色背景 = 勝率 ≥ 80%
- 熱力圖：越深紅報酬越高，越深綠虧損越深
    """)
    st.divider()
    st.markdown("### 觀察天數說明")
    st.markdown("""
| 天數 | 約等於 | 意義 |
|------|--------|------|
| 10天 | 2週 | 短線反彈 |
| 20天 | 1個月 | 月線修復 |
| 50天 | 2.5個月 | 季線修復 |
| 100天 | 5個月 | 半年趨勢 |
| 200天 | 1年 | 年線修復 |
    """)
    st.warning("本系統為輔助研究工具，不構成投資建議。歷史回測不代表未來績效。")

# ==============================
# TAB 3: 系統檢核
# ==============================
with tab3:
    st.subheader("🔧 系統檢核")
    st.info("自動驗證資料源、API連線、程式邏輯與資料新鮮度是否正常")

    if st.button("▶️ 執行系統檢核", type="primary", key="check"):
        checks = []

        def run_check(name, fn):
            try:
                ok, detail = fn()
                checks.append({"項目": name, "狀態": "✅ 正常" if ok else "❌ 異常", "說明": detail})
            except Exception as e:
                checks.append({"項目": name, "狀態": "❌ 失敗", "說明": str(e)[:120]})

        with st.spinner("執行中（約1~2分鐘）..."):

            def check_moneydj():
                funds = get_moneydj_fund_list("BFZ002")
                ok = len(funds) > 0
                return ok, "MoneyDJ安聯投信清單：取得 " + str(len(funds)) + " 檔" if ok else "無法取得基金清單"
            run_check("MoneyDJ基金清單API（安聯投信）", check_moneydj)

            def check_yahoo_search():
                code = get_yahoo_code("安聯收益成長")
                ok = code is not None and ":FO" in str(code)
                return ok, "搜尋「安聯收益成長」→ Yahoo代碼：" + str(code) if ok else "搜尋API無回應或找不到代碼"
            run_check("Yahoo Finance搜尋API（基金代碼對應）", check_yahoo_search)

            def check_yahoo_nav():
                prices = get_nav_recent("F00000VHRD:FO")
                ok = len(prices) >= 10
                if ok:
                    d = sorted(prices.keys())
                    return True, "安聯收益成長AM美元：最新淨值 " + str(prices[d[-1]]) + "（" + d[-1] + "）｜取得 " + str(len(prices)) + " 筆"
                return False, "資料筆數不足：" + str(len(prices))
            run_check("Yahoo Finance淨值API（安聯收益成長AM美元）", check_yahoo_nav)

            def check_freshness():
                prices = get_nav_recent("F00000VHRD:FO")
                if not prices:
                    return False, "無法取得資料"
                latest_date = sorted(prices.keys())[-1]
                days_diff = (datetime.today() - datetime.strptime(latest_date, "%Y-%m-%d")).days
                ok = days_diff <= 5
                return ok, "最新資料日期：" + latest_date + "（距今 " + str(days_diff) + " 天）" + ("✓" if ok else " ⚠️ 可能延遲")
            run_check("資料新鮮度（最新淨值距今天數）", check_freshness)

            def check_history():
                prices = get_nav_history("F00000VHRD:FO")
                ok = len(prices) > 500
                if ok:
                    d = sorted(prices.keys())
                    return True, "安聯收益成長AM美元：取得 " + str(len(prices)) + " 個交易日（" + d[0] + " ~ " + d[-1] + "）"
                return False, "歷史資料不足：" + str(len(prices)) + " 筆（預期 >500）"
            run_check("歷史淨值資料量（15年）", check_history)

            def check_logic():
                tp = {(datetime.today() - timedelta(days=20-i)).strftime("%Y-%m-%d"):
                      (100.0 if i < 11 else 88.0) for i in range(20)}
                ret, _, _ = calc_rolling_latest(tp, -10)
                ok = ret is not None and abs(ret - (-12.0)) < 0.01
                return ok, "計算結果：{:.2f}%（預期 -12.00%）{}".format(ret or 0, "✓" if ok else "✗")
            run_check("滾動10日報酬計算邏輯", check_logic)

            def check_backtest_trigger():
                prices = get_nav_history("F00000VHRD:FO")
                if not prices:
                    return False, "無法抓取資料"
                result = run_backtest(prices, -5)
                if result and result["total"] > 0:
                    return True, "安聯收益成長AM美元 @-5%：觸發 " + str(result["total"]) + " 次，最長連續 " + str(result["max_consec"]) + " 天"
                return False, "觸發次數為0，資料可能有問題"
            run_check("回測觸發驗證（安聯收益成長 @-5%）", check_backtest_trigger)

        show_html(pd.DataFrame(checks))
        all_ok = all("✅" in c["狀態"] for c in checks)
        if all_ok:
            st.success("✅ 所有系統檢核通過！")
        else:
            failed = [c["項目"] for c in checks if "❌" in c["狀態"]]
            st.error("❌ 異常項目：" + "、".join(failed))
