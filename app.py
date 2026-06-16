import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re

st.set_page_config(page_title="台灣基金滾動10日跌幅系統", layout="wide")
st.title("📉 台灣基金滾動10日跌幅系統")
st.caption("資料來源：MoneyDJ | 更新時間：" + datetime.now().strftime("%Y-%m-%d %H:%M"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.moneydj.com/funddj/",
}

FUND_TYPES = {
    "境內基金": "https://www.moneydj.com/funddj/ya/yp082000.djhtm",
    "境外基金": "https://www.moneydj.com/funddj/ya/yp081001.djhtm",
}

COMPANY_URLS = {
    "境內-兆豐投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0001",
    "境內-第一金投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0003",
    "境內-元大投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0005",
    "境內-統一投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0009",
    "境內-富邦投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0010",
    "境內-群益投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0016",
    "境內-復華投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0022",
    "境內-中國信託投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0026",
    "境內-國泰投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0037",
    "境內-凱基投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0041",
    "境內-台新投信": "https://www.moneydj.com/funddj/ya/yp082000.djhtm?a=A0047",
    "境內-全部": "https://www.moneydj.com/funddj/ya/yp082000.djhtm",
    "境外-全部": "https://www.moneydj.com/funddj/ya/yp081001.djhtm",
}

@st.cache_data(ttl=86400)
def get_fund_list(url, is_domestic):
    funds = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
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
                        funds.append({
                            "code": code,
                            "name": name,
                            "type": "境內" if is_domestic else "境外",
                            "url": "https://www.moneydj.com" + href if href.startswith("/") else href
                        })
    except Exception as e:
        st.warning("抓取基金清單失敗：" + str(e))
    return funds

def get_nav_history(code, is_domestic, days=60):
    page = "yp010000" if is_domestic else "yp010001"
    url = "https://www.moneydj.com/funddj/ya/" + page + ".djhtm?a=" + code
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = "big5"
        soup = BeautifulSoup(res.text, "html.parser")
        prices = {}
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    date_text = cells[0].get_text(strip=True)
                    nav_text = cells[1].get_text(strip=True).replace(",", "")
                    if re.match(r"^\d{2}/\d{2}$", date_text):
                        try:
                            nav = float(nav_text)
                            year = datetime.now().year
                            date_full = str(year) + "/" + date_text
                            dt = datetime.strptime(date_full, "%Y/%m/%d")
                            if dt > datetime.now():
                                dt = dt.replace(year=year - 1)
                            prices[dt.strftime("%Y-%m-%d")] = nav
                        except:
                            pass
        return prices
    except:
        return {}

def get_nav_history_15y(code, is_domestic):
    page = "yp010000" if is_domestic else "yp010001"
    base_url = "https://www.moneydj.com/funddj/ya/" + page + ".djhtm?a=" + code
    all_prices = {}
    try:
        res = requests.get(base_url, headers=HEADERS, timeout=15)
        res.encoding = "big5"
        soup = BeautifulSoup(res.text, "html.parser")
        current_year = datetime.now().year
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    date_text = cells[0].get_text(strip=True)
                    nav_text = cells[1].get_text(strip=True).replace(",", "")
                    if re.match(r"^\d{2}/\d{2}$", date_text):
                        try:
                            nav = float(nav_text)
                            date_full = str(current_year) + "/" + date_text
                            dt = datetime.strptime(date_full, "%Y/%m/%d")
                            if dt > datetime.now():
                                dt = dt.replace(year=current_year - 1)
                            all_prices[dt.strftime("%Y-%m-%d")] = nav
                        except:
                            pass
        for year in range(current_year - 1, current_year - 16, -1):
            for month in [1, 4, 7, 10]:
                date_str = str(year) + str(month).zfill(2) + "01"
                hist_url = ("https://www.moneydj.com/funddj/ya/" + page +
                           ".djhtm?a=" + code + "&d=" + date_str)
                try:
                    res2 = requests.get(hist_url, headers=HEADERS, timeout=10)
                    res2.encoding = "big5"
                    soup2 = BeautifulSoup(res2.text, "html.parser")
                    for table in soup2.find_all("table"):
                        rows = table.find_all("tr")
                        for row in rows:
                            cells = row.find_all("td")
                            if len(cells) >= 2:
                                date_text = cells[0].get_text(strip=True)
                                nav_text = cells[1].get_text(strip=True).replace(",", "")
                                if re.match(r"^\d{4}/\d{2}/\d{2}$", date_text) or \
                                   re.match(r"^\d{2}/\d{2}$", date_text):
                                    try:
                                        nav = float(nav_text)
                                        if re.match(r"^\d{2}/\d{2}$", date_text):
                                            date_full = str(year) + "/" + date_text
                                            dt = datetime.strptime(date_full, "%Y/%m/%d")
                                        else:
                                            dt = datetime.strptime(date_text, "%Y/%m/%d")
                                        all_prices[dt.strftime("%Y-%m-%d")] = nav
                                    except:
                                        pass
                    time.sleep(0.3)
                except:
                    pass
    except:
        pass
    return all_prices

def calc_rolling_return_latest(prices_dict):
    if len(prices_dict) < 11:
        return None
    dates = sorted(prices_dict.keys())
    latest = prices_dict[dates[-1]]
    base = prices_dict[dates[-11]]
    if base == 0:
        return None
    return (latest - base) / base * 100

def calc_all_rolling_returns(prices_dict):
    if len(prices_dict) < 11:
        return []
    dates = sorted(prices_dict.keys())
    results = []
    for i in range(10, len(dates)):
        base_price = prices_dict[dates[i - 10]]
        curr_price = prices_dict[dates[i]]
        if base_price > 0:
            ret = (curr_price - base_price) / base_price * 100
            results.append({
                "date": dates[i],
                "base_date": dates[i - 10],
                "base_price": base_price,
                "curr_price": curr_price,
                "return": round(ret, 2)
            })
    return results

def run_backtest(prices_dict, threshold):
    rolling = calc_all_rolling_returns(prices_dict)
    if not rolling:
        return None
    dates = sorted(prices_dict.keys())
    date_to_idx = {d: i for i, d in enumerate(dates)}
    HORIZONS = [10, 20, 50, 100, 200]
    triggers = [r for r in rolling if r["return"] <= threshold]
    if not triggers:
        return None

    trigger_dates = set(t["date"] for t in triggers)
    max_consec = 0
    cc = 0
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
                horizon_rets[h].append({"ret": round(ret, 2), "year": year, "date": t["date"]})
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
        "triggers": triggers,
        "trigger_dates": list(trigger_dates),
        "max_consec": max_consec,
        "horizon_rets": horizon_rets,
        "horizon_dds": horizon_dds,
        "yearly": yearly,
        "total": len(triggers),
        "HORIZONS": HORIZONS,
    }

def color_ret(val):
    if val is None or str(val) in ["", "---", "待觀察"]:
        return ""
    try:
        v = float(str(val).replace("%", ""))
        return "color: green; font-weight: bold" if v > 0 else "color: red; font-weight: bold"
    except:
        return ""

def color_dd(val):
    if val is None or str(val) in ["", "---", "待觀察"]:
        return ""
    try:
        v = float(str(val).replace("%", ""))
        return "color: red; font-weight: bold" if v < 0 else ""
    except:
        return ""

def fmt(v):
    if v is None:
        return "待觀察"
    return "{:.2f}%".format(v)

tab0, tab1, tab2 = st.tabs(["🔍 每日警示掃描", "📊 個基金回測", "📖 使用說明"])

with tab0:
    st.subheader("每日警示掃描")
    col1, col2 = st.columns([2, 1])
    with col1:
        scope = st.selectbox("選擇範圍", list(COMPANY_URLS.keys()))
    with col2:
        threshold1 = st.slider("警示門檻（跌幅%）", min_value=-30, max_value=-3, value=-10, step=1, key="t1")

    if st.button("🔍 開始掃描", type="primary", key="scan"):
        url = COMPANY_URLS[scope]
        is_domestic = "境內" in scope
        with st.spinner("抓取基金清單..."):
            funds = get_fund_list(url, is_domestic)

        if not funds:
            st.error("無法取得基金清單，請稍後再試")
        else:
            total = len(funds)
            st.info("共 " + str(total) + " 檔，開始掃描...")
            results = []
            progress = st.progress(0)
            status = st.empty()

            for i, fund in enumerate(funds):
                status.text("掃描：" + fund["name"][:20] + "（" + str(i+1) + "/" + str(total) + "）")
                prices = get_nav_history(fund["code"], fund["type"] == "境內")
                ret = calc_rolling_return_latest(prices)
                if ret is not None and ret <= threshold1:
                    results.append({
                        "類型": fund["type"],
                        "基金名稱": fund["name"],
                        "代碼": fund["code"],
                        "滾動10日報酬率": "{:.2f}%".format(ret),
                        "數值": ret
                    })
                progress.progress((i + 1) / total)
                time.sleep(0.3)

            progress.empty()
            status.empty()

            if results:
                df = pd.DataFrame(results).sort_values("數值").drop(columns=["數值"])
                st.error("⚠️ 共 " + str(len(results)) + " 檔觸發（門檻：" + str(threshold1) + "%）")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button("📥 下載CSV", df.to_csv(index=False).encode("utf-8-sig"), "fund_alert.csv", "text/csv")
            else:
                st.success("✅ 目前無基金觸發 " + str(threshold1) + "% 警示")

with tab1:
    st.subheader("個基金回測（15年）")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        fund_code = st.text_input("輸入MoneyDJ基金代碼", value="TLZ64", help="例：TLZ64（安聯收益成長AM美元）")
    with col2:
        fund_type = st.radio("基金類型", ["境外", "境內"], horizontal=True)
    with col3:
        threshold2 = st.slider("觸發門檻（跌幅%）", min_value=-30, max_value=-3, value=-10, step=1, key="t2")

    if st.button("🔬 開始分析", type="primary", key="backtest"):
        is_dom = fund_type == "境內"
        with st.spinner("抓取歷史淨值中（15年資料需要較長時間）..."):
            prices = get_nav_history_15y(fund_code, is_dom)

        if not prices or len(prices) < 11:
            st.error("資料不足，請確認代碼是否正確")
            st.info("提示：可到 moneydj.com/funddj 搜尋基金，從網址列取得代碼（?a=後面的部分）")
        else:
            st.success("成功抓取 " + str(len(prices)) + " 個交易日（" + min(prices.keys()) + " ~ " + max(prices.keys()) + "）")
            result = run_backtest(prices, threshold2)

            if not result:
                st.warning("此期間無觸發紀錄")
            else:
                HORIZONS = result["HORIZONS"]
                st.markdown("### 📊 統計總覽（最長連續觸發：" + str(result["max_consec"]) + " 天，總觸發：" + str(result["total"]) + " 次）")

                win_row = {"項目": "勝率"}
                avg_row = {"項目": "平均單次報酬%（表B）"}
                cum_row = {"項目": "累積報酬%（表C）"}
                dd_row = {"項目": "平均最大回撤%（表E）"}

                for h in HORIZONS:
                    rets = [x["ret"] for x in result["horizon_rets"][h]]
                    dds = [x["dd"] for x in result["horizon_dds"][h]]
                    col = str(h) + "天"
                    if not rets:
                        win_row[col] = "待觀察"
                        avg_row[col] = "待觀察"
                        cum_row[col] = "待觀察"
                        dd_row[col] = "待觀察"
                    else:
                        wins = sum(1 for r in rets if r > 0)
                        win_row[col] = "{:.2f}%".format(wins / len(rets) * 100)
                        avg_row[col] = "{:.2f}%".format(sum(rets) / len(rets))
                        cum_row[col] = "{:.2f}%".format(sum(rets))
                        dd_row[col] = "{:.2f}%".format(sum(dds) / len(dds))

                df_summary = pd.DataFrame([win_row, avg_row, cum_row, dd_row])
                ret_cols = [c for c in df_summary.columns if "天" in c]
                st.dataframe(df_summary.style.map(color_ret, subset=ret_cols), use_container_width=True, hide_index=True)

                st.markdown("### 📅 年度明細")
                yearly_rows = []
                for year in sorted(result["yearly"].keys()):
                    y = result["yearly"][year]
                    row = {"年度": year, "觸發次數": len(y["trigger_dates"]), "最長連續觸發": y["max_consec"]}
                    for h in HORIZONS:
                        rets = y["rets"][h]
                        dds = y["dds"][h]
                        row[str(h) + "天平均%"] = fmt(round(sum(rets)/len(rets), 2) if rets else None)
                        row[str(h) + "天累積%"] = fmt(round(sum(rets), 2) if rets else None)
                        row[str(h) + "天回撤%"] = fmt(round(sum(dds)/len(dds), 2) if dds else None)
                    yearly_rows.append(row)

                total_row = {"年度": "合計/平均", "觸發次數": result["total"], "最長連續觸發": result["max_consec"]}
                for h in HORIZONS:
                    rets = [x["ret"] for x in result["horizon_rets"][h]]
                    dds = [x["dd"] for x in result["horizon_dds"][h]]
                    total_row[str(h) + "天平均%"] = fmt(round(sum(rets)/len(rets), 2) if rets else None)
                    total_row[str(h) + "天累積%"] = fmt(round(sum(rets), 2) if rets else None)
                    total_row[str(h) + "天回撤%"] = fmt(round(sum(dds)/len(dds), 2) if dds else None)
                yearly_rows.append(total_row)

                df_yearly = pd.DataFrame(yearly_rows)
                ret_cols_y = [c for c in df_yearly.columns if "平均%" in c or "累積%" in c]
                dd_cols_y = [c for c in df_yearly.columns if "回撤%" in c]
                styled = df_yearly.style.map(color_ret, subset=ret_cols_y).map(color_dd, subset=dd_cols_y)
                st.dataframe(styled, use_container_width=True, hide_index=True)

                st.info(
                    "計算邏輯說明：\n"
                    "- 每個觸發日各自進場，連續觸發N天即有N筆紀錄\n"
                    "- 表B（平均%）：所有觸發單次報酬的算術平均\n"
                    "- 表C（累積%）：所有觸發報酬直接加總，不除筆數\n"
                    "- 表E（回撤%）：持有期間內最深跌幅的平均\n"
                    "- 待觀察：觸發後未滿觀察天數，不計入統計"
                )

with tab2:
    st.markdown("## 使用說明")
    st.info("資料來源：MoneyDJ基智網 | 境內基金+境外基金全市場涵蓋")
    st.markdown("""
### 如何找到基金代碼？
1. 前往 `moneydj.com/funddj`
2. 搜尋你想查的基金
3. 點入基金頁面後，網址列 `?a=` 後面的英數字就是代碼
4. 例如：安聯收益成長AM美元 = `TLZ64`

### 每日警示掃描
- 選擇投信公司或全市場範圍
- 設定觸發門檻（預設-10%）
- 點「開始掃描」，系統會逐一檢查每檔基金的滾動10日報酬率

### 個基金回測
- 輸入MoneyDJ代碼
- 選擇境內或境外
- 系統嘗試抓取最長15年歷史淨值
- 顯示各年度觸發次數、勝率、報酬統計

### 注意事項
- 共同基金淨值為T+1公告，每日更新一次
- 本系統為研究工具，不構成投資建議
- 歷史回測不代表未來績效
    """)
    st.warning("MoneyDJ資料為爬蟲方式取得，若網站改版可能影響功能")
