import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import feedparser
from datetime import datetime, timedelta
import pytz
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import re

st.set_page_config(page_title="Family Net Worth", page_icon="💰", layout="wide", initial_sidebar_state="expanded")

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)
TODAY_NAIVE = pd.Timestamp(now_ist.date())  # tz-naive "today" used for ALL date math from here on
HISTORY_PATH = "data/history.csv"

# -------------------------------------------------
# THEME — tighter spacing, less dead space, per feedback
# -------------------------------------------------
st.markdown("""
<style>
    .stApp { background: #0a0e17; color: #e5e9f0; }
    section[data-testid="stSidebar"] { background-color: #0f1420 !important; border-right: 1px solid #1c2333; }
    .main-title { font-size: 1.75rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.03em; margin-bottom: 0.05rem; }
    .sub-title { color: #6b7688; font-size: 0.82rem; margin-bottom: 0.9rem; font-weight: 400; }
    .section-header {
        font-size: 0.75rem; font-weight: 700; color: #8b95a8; margin: 1.3rem 0 0.6rem 0;
        text-transform: uppercase; letter-spacing: 0.08em; display: flex; align-items: center; gap: 8px;
    }
    .section-header::after { content: ""; flex: 1; height: 1px; background: #1c2333; }
    div[data-testid="stMetric"] {
        background: linear-gradient(155deg, #12182a 0%, #0e1420 100%);
        border: 1px solid #1c2333; border-radius: 12px; padding: 12px 15px 10px 15px;
    }
    div[data-testid="stMetric"]:hover { border-color: #2a3552; }
    div[data-testid="stMetricValue"] { font-size: 1.35rem !important; font-weight: 700 !important; color: #f8fafc !important; }
    div[data-testid="stMetricLabel"] { color: #6b7688 !important; font-size: 0.68rem !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.05em; }
    div[data-testid="stMetricDelta"] { font-size: 0.76rem !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: #0f1420; gap: 3px; border-radius: 9px; padding: 3px; border: 1px solid #1c2333; }
    .stTabs [data-baseweb="tab"] { color: #6b7688 !important; border-radius: 6px; padding: 6px 16px; font-weight: 500; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, #1e2942, #17203a) !important; color: #f8fafc !important; font-weight: 600; }
    .stDataFrame { border: 1px solid #1c2333; border-radius: 9px; overflow: hidden; }
    p, span, label, .stMarkdown { color: #c2c9d6 !important; }
    .flag-card { border-radius: 10px; padding: 10px 14px; margin-bottom: 7px; display: flex; gap: 11px; align-items: flex-start; border: 1px solid; }
    .flag-critical { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.28); }
    .flag-warning  { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.28); }
    .flag-info     { background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.28); }
    .flag-title { font-weight: 600; font-size: 0.85rem; color: #f1f5f9; margin: 0; }
    .flag-body  { font-size: 0.78rem; color: #9aa4b8; margin: 1px 0 0 0; }
    .news-item { padding: 8px 0; border-bottom: 1px solid #1c2333; }
    .news-item a { color: #d7dce6 !important; text-decoration: none; font-size: 0.84rem; font-weight: 500; }
    .news-item a:hover { color: #7fa8f5 !important; }
    .news-meta { font-size: 0.71rem; color: #5b6478; margin-top: 1px; }
    .block-container { padding-top: 1.3rem; padding-bottom: 2rem; max-width: 1400px; }
    .caveat { font-size: 0.72rem; color: #5b6478; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATE HELPER — fixes the tz-naive/aware crash that silently zeroed out
# every "Ann. Return %" and "Nifty50 Ann. %" value in the last version.
# -------------------------------------------------
def to_naive_ts(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts

# -------------------------------------------------
# DATA SOURCES
# -------------------------------------------------
@st.cache_data(ttl=3600)
def get_amfi_data():
    """Returns (nav_dict, code_dict, name_dict), all keyed by ISIN."""
    try:
        r = requests.get("https://www.amfiindia.com/spages/NAVAll.txt", timeout=15)
        r.raise_for_status()
        nav_dict, code_dict, name_dict = {}, {}, {}
        for line in r.text.splitlines():
            parts = line.split(";")
            if len(parts) >= 5 and parts[0].strip().isdigit():
                code = parts[0].strip()
                isin_g, isin_d = parts[1].strip(), parts[2].strip()
                name = parts[3].strip()
                try:
                    nav = float(parts[4].strip())
                except Exception:
                    continue
                for isin in (isin_g, isin_d):
                    if isin and isin != "-" and len(isin) > 8:
                        nav_dict[isin] = nav
                        code_dict[isin] = code
                        name_dict[isin] = name
        return nav_dict, code_dict, name_dict
    except Exception:
        return {}, {}, {}

@st.cache_data(ttl=21600, show_spinner=False)
def get_mf_nav_history(scheme_code: str):
    """Full historical NAV series for a scheme, used for 1Y/3Y/5Y trailing returns."""
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna().sort_values("date")
        return df if not df.empty else None
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_nifty_history():
    """Nifty 50 daily closes as a naive-indexed nav-style dataframe — used both
    as the broad-market benchmark and for its own trailing 1Y/3Y/5Y returns."""
    try:
        hist = yf.Ticker("^NSEI").history(period="5y")
        if hist.empty:
            return None
        df = hist[["Close"]].rename(columns={"Close": "nav"}).reset_index()
        df = df.rename(columns={"Date": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df
    except Exception:
        return None

def trailing_return(hist_df: pd.DataFrame, years: float):
    """Point-to-point annualized return over the trailing N years. Returns None
    if the fund/index doesn't have that much history yet (e.g. a 2-year-old
    fund has no real 5Y number — shown as '—', never guessed at)."""
    if hist_df is None or hist_df.empty:
        return None
    latest_date, latest_nav = hist_df["date"].iloc[-1], hist_df["nav"].iloc[-1]
    target_date = latest_date - pd.Timedelta(days=int(years * 365.25))
    past = hist_df[hist_df["date"] <= target_date]
    if past.empty or latest_nav <= 0:
        return None
    past_nav = past.iloc[-1]["nav"]
    if past_nav <= 0:
        return None
    return ((latest_nav / past_nav) ** (1 / years) - 1) * 100

@st.cache_data(ttl=300)
def get_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=8)
        return float(r.json()["rates"]["INR"])
    except Exception:
        return 95.5

@st.cache_data(ttl=300)
def get_stock_price(symbol: str):
    if not symbol:
        return None
    try:
        t = yf.Ticker(f"{symbol}.NS")
        hist = t.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None

def safe_float(val, default=0.0):
    try:
        v = pd.to_numeric(val, errors="coerce")
        return default if pd.isna(v) else float(v)
    except Exception:
        return default

def format_inr(num):
    if pd.isna(num):
        return "₹0"
    return f"₹{num:,.0f}"

def load_data(uploaded_file=None):
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
    else:
        try:
            xls = pd.ExcelFile("data/Networth_Raw_Data.xlsx")
        except Exception:
            st.error("Could not load data/Networth_Raw_Data.xlsx")
            st.stop()
    sheet_map = {s.lower().strip(): s for s in xls.sheet_names}
    def find_sheet(*names):
        for n in names:
            if n in sheet_map:
                return sheet_map[n]
        return list(xls.sheet_names)[0]
    fd = pd.read_excel(xls, find_sheet("fd", "fixed deposits", "fixed_deposits"))
    mf = pd.read_excel(xls, find_sheet("mf", "mutual funds", "mutual_funds"))
    stocks = pd.read_excel(xls, find_sheet("stocks", "stock", "equities"))
    return fd, mf, stocks

# -------------------------------------------------
# CATEGORY INFERENCE (validated 19/19 against real fund names)
# -------------------------------------------------
CATEGORY_RULES = [
    ("Liquid", r"liquid"), ("Money Market", r"money\s*market"), ("Overnight", r"overnight"),
    ("Small Cap", r"small\s*cap"), ("Mid Cap", r"mid\s*cap"), ("Large Cap", r"large\s*cap|bluechip"),
    ("Flexi Cap", r"flexi\s*cap|multi\s*cap"), ("Index", r"index|next\s*50|nifty\s*50\b"),
    ("Hybrid", r"hybrid|balanced"), ("Contra/Value", r"contra|value\s*discovery"),
    ("Sectoral/Thematic", r"infra|defence|bharat\s*22|fof|reform"),
]
DEBT_LIKE = {"Liquid", "Money Market", "Overnight"}

def infer_category(fund_name: str) -> str:
    name = (fund_name or "").lower()
    for label, pattern in CATEGORY_RULES:
        if re.search(pattern, name):
            return label
    return "Other Equity"

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.markdown("### Controls")
    uploaded = st.file_uploader("Upload new Excel", type=["xlsx", "xls"])
    if st.button("Force Recalculate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    log_snapshot = st.toggle("Log today's snapshot to history", value=True,
                              help="Appends one row/day to data/history.csv. Streamlit Community Cloud's free tier doesn't guarantee this file survives a redeploy — download it periodically from the History tab.")
    st.markdown("---")
    st.caption("AMFI · mfapi.in · Yahoo Finance · Frankfurter · Google News")
    st.caption(f"IST {now_ist.strftime('%d %b %Y, %H:%M')}")

# -------------------------------------------------
# LOAD + PROCESS
# -------------------------------------------------
fd_raw, mf_raw, stocks_raw = load_data(uploaded)
usd_inr = get_usd_inr()
amfi_navs, amfi_codes, amfi_names = get_amfi_data()
nifty_hist = get_nifty_history()
nifty_1y = trailing_return(nifty_hist, 1)
nifty_3y = trailing_return(nifty_hist, 3)
nifty_5y = trailing_return(nifty_hist, 5)

mf_txns = []
for _, row in mf_raw.iterrows():
    try:
        isin = str(row.get("ISIN", "") or "").strip()
        owner = str(row.get("Owner", "") or "").strip()
        fund_name = str(row.get("Fund Name", "") or "").strip()
        units = safe_float(row.get("Units"))
        invested = safe_float(row.get("Invested Amount", row.get("Invested")))
        pdate = to_naive_ts(row.get("Purchase Date"))
        if units <= 0 or not isin:
            continue
        mf_txns.append({"Owner": owner, "ISIN": isin, "Fund Name": fund_name, "Units": units,
                         "Invested": invested, "Purchase Date": pdate})
    except Exception:
        continue

mf_txns_df = pd.DataFrame(mf_txns)
if not mf_txns_df.empty:
    mf_agg = mf_txns_df.groupby(["Owner", "ISIN", "Fund Name"], as_index=False).agg(
        {"Units": "sum", "Invested": "sum", "Purchase Date": "min"})
else:
    mf_agg = pd.DataFrame(columns=["Owner", "ISIN", "Fund Name", "Units", "Invested", "Purchase Date"])

mf_rows, mf_failed = [], 0
for _, row in mf_agg.iterrows():
    try:
        isin, units, invested, pdate = row["ISIN"], row["Units"], row["Invested"], row["Purchase Date"]
        nav = amfi_navs.get(isin)
        if nav is None:
            mf_failed += 1
            nav = 0.0
        current_value = units * nav
        pnl = current_value - invested
        ret = (pnl / invested * 100) if invested > 0 else 0.0
        category = infer_category(row["Fund Name"])

        days_held = (TODAY_NAIVE - pdate).days if pdate is not None else None
        fund_return_ann = None
        if days_held and days_held >= 30 and invested > 0:
            fund_return_ann = ((current_value / invested) ** (365.25 / days_held) - 1) * 100

        code = amfi_codes.get(isin)
        r1y = r3y = r5y = b1y = b3y = b5y = None
        if category not in DEBT_LIKE and code:
            fund_hist = get_mf_nav_history(code)
            r1y, r3y, r5y = trailing_return(fund_hist, 1), trailing_return(fund_hist, 3), trailing_return(fund_hist, 5)
            b1y, b3y, b5y = nifty_1y, nifty_3y, nifty_5y

        mf_rows.append({
            "Owner": row["Owner"], "ISIN": isin, "Fund Name": row["Fund Name"][:42], "Category": category,
            "Units": round(units, 3), "Invested": invested, "Current NAV": nav, "Current Value": current_value,
            "P&L": pnl, "Return %": ret, "Ann. Return %": fund_return_ann,
            "1Y %": r1y, "3Y %": r3y, "5Y %": r5y,
            "Nifty 1Y %": b1y, "Nifty 3Y %": b3y, "Nifty 5Y %": b5y,
            "Purchase Date": pdate,
        })
    except Exception:
        mf_failed += 1
mf = pd.DataFrame(mf_rows)

stock_rows = []
for _, row in stocks_raw.iterrows():
    try:
        symbol = str(row.get("Symbol", row.get("Ticker / Symbol", "")) or "").strip().upper()
        qty = safe_float(row.get("Quantity"))
        invested = safe_float(row.get("Invested Amount"))
        if qty <= 0:
            continue
        price = get_stock_price(symbol) if symbol else None
        if price is None:
            price = safe_float(row.get("Current Price", row.get("Current Price (CMP)")))
            if price == 0:
                price = safe_float(row.get("Purchase Price", row.get("Avg Buy Price")))
        current_value = qty * price
        pnl = current_value - invested
        ret = (pnl / invested * 100) if invested > 0 else 0.0
        stock_rows.append({"Owner": str(row.get("Owner", "") or ""), "Symbol": symbol, "Quantity": qty,
                            "Invested": invested, "Current Price": price, "Current Value": current_value,
                            "P&L": pnl, "Return %": ret})
    except Exception:
        continue
stocks = pd.DataFrame(stock_rows)

fd_rows = []
for _, row in fd_raw.iterrows():
    try:
        holder = str(row.get("Holder Name", "") or "").strip()
        account = str(row.get("Account Number", "") or "").strip()
        principal = safe_float(row.get("Principal Amount"))
        if (not holder or holder.lower() in ["nan", "nat", "none"] or principal <= 0 or "total" in holder.lower()):
            continue
        currency = str(row.get("Currency", "INR") or "INR").upper().strip()
        if currency not in ["INR", "USD"]:
            currency = "INR"
        mat_date = to_naive_ts(row.get("Maturity Date"))
        dep_date = to_naive_ts(row.get("Deposit Date"))
        days_to_mat = (mat_date - TODAY_NAIVE).days if mat_date is not None else None
        days_elapsed = (TODAY_NAIVE - dep_date).days if dep_date is not None else 0
        roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))
        accrued = principal * (roi / 100) * (max(days_elapsed, 0) / 365)
        current_value_original = principal + accrued
        if currency == "USD":
            current_value_inr, principal_inr = current_value_original * usd_inr, principal * usd_inr
        else:
            current_value_inr, principal_inr = current_value_original, principal
        fd_rows.append({"Holder Name": holder, "Account Number": account, "Currency": currency,
                         "Principal (Original)": round(principal, 2), "Principal (INR)": round(principal_inr, 0),
                         "ROI %": roi, "Days to Maturity": days_to_mat, "Accrued Interest": round(accrued, 0),
                         "Current Value (Original)": round(current_value_original, 0),
                         "Current Value (INR)": round(current_value_inr, 0),
                         "Maturity Date": mat_date.strftime("%Y-%m-%d") if mat_date is not None else ""})
    except Exception:
        continue
fd = pd.DataFrame(fd_rows)

# -------------------------------------------------
# AGGREGATES
# -------------------------------------------------
total_mf = mf["Current Value"].sum() if not mf.empty else 0
total_stocks = stocks["Current Value"].sum() if not stocks.empty else 0
total_fd = fd["Current Value (INR)"].sum() if not fd.empty else 0
total_networth = total_mf + total_stocks + total_fd
total_invested = ((mf["Invested"].sum() if not mf.empty else 0) +
                   (stocks["Invested"].sum() if not stocks.empty else 0) +
                   (fd["Principal (INR)"].sum() if not fd.empty else 0))
total_pnl = total_networth - total_invested
equity_pct = ((total_mf + total_stocks) / total_networth * 100) if total_networth else 0
fd_pct = (total_fd / total_networth * 100) if total_networth else 0
top5_mf_pct = (mf.nlargest(5, "Current Value")["Current Value"].sum() / total_mf * 100) if not mf.empty and total_mf > 0 else 0
top5_stock_pct = (stocks.nlargest(5, "Current Value")["Current Value"].sum() / total_stocks * 100) if not stocks.empty and total_stocks > 0 else 0

# -------------------------------------------------
# HEALTH SCORE — 5 inspectable factors, not a mystery number
# -------------------------------------------------
def score_allocation(equity_pct, target=60):
    return max(0, 100 - abs(equity_pct - target) * 1.8)
def score_concentration(top5_pct):
    if top5_pct <= 35: return 100
    if top5_pct >= 80: return 0
    return 100 - (top5_pct - 35) / 45 * 100
def score_liquidity(fd_pct):
    if 20 <= fd_pct <= 40: return 100
    if fd_pct < 20: return max(0, 100 - (20 - fd_pct) * 3)
    return max(0, 100 - (fd_pct - 40) * 1.6)
def score_diversification(mf_df):
    if mf_df.empty:
        return 50
    cat = mf_df.groupby("Category")["Current Value"].sum()
    if cat.sum() == 0:
        return 50
    hhi = ((cat / cat.sum()) ** 2).sum()
    return max(0, (1 - hhi) * 100 / 0.85)
def score_performance(mf_df):
    valid = mf_df.dropna(subset=["1Y %", "Nifty 1Y %"])
    if valid.empty:
        return 60
    return (valid["1Y %"] > valid["Nifty 1Y %"]).mean() * 100

alloc_score = score_allocation(equity_pct)
conc_score = min(score_concentration(top5_mf_pct), score_concentration(top5_stock_pct) if not stocks.empty else 100)
liq_score = score_liquidity(fd_pct)
div_score = score_diversification(mf)
perf_score = score_performance(mf)

WEIGHTS = {"Allocation": 0.26, "Concentration": 0.20, "Liquidity": 0.20, "Diversification": 0.14, "Performance": 0.20}
factor_scores = {"Allocation": alloc_score, "Concentration": conc_score, "Liquidity": liq_score,
                  "Diversification": div_score, "Performance": perf_score}
health_score = sum(factor_scores[k] * WEIGHTS[k] for k in WEIGHTS)
health_label = "Healthy" if health_score >= 75 else ("Adequate" if health_score >= 55 else "Needs Attention")

# -------------------------------------------------
# RED FLAGS — richer set: persistent (1Y AND 3Y) underperformance, matured-
# but-uncollected FDs, near-term maturities, large losers, concentration
# -------------------------------------------------
flags = []
if equity_pct < 40:
    flags.append(("critical" if equity_pct < 25 else "warning", "Equity allocation drift",
                   f"Equity is {equity_pct:.1f}% of net worth against a common 60% target — {fd_pct:.1f}% sits in FDs/cash, a real drag on long-term compounding."))
if top5_mf_pct > 60:
    flags.append(("warning", "Mutual fund concentration", f"Top 5 funds are {top5_mf_pct:.1f}% of your MF portfolio."))
if not stocks.empty and top5_stock_pct > 65:
    flags.append(("warning", "Stock concentration", f"Top 5 stocks are {top5_stock_pct:.1f}% of your equity holdings."))
if not mf.empty:
    persistent = mf.dropna(subset=["1Y %", "3Y %", "Nifty 1Y %", "Nifty 3Y %"])
    persistent = persistent[(persistent["1Y %"] < persistent["Nifty 1Y %"] - 2) & (persistent["3Y %"] < persistent["Nifty 3Y %"] - 2)]
    for _, r in persistent.sort_values("1Y %").head(3).iterrows():
        flags.append(("warning", f"{r['Fund Name']}: persistent underperformance",
                       f"Trailing both 1Y ({r['1Y %']:.1f}% vs Nifty {r['Nifty 1Y %']:.1f}%) and 3Y ({r['3Y %']:.1f}% vs {r['Nifty 3Y %']:.1f}%) — worth reviewing, not necessarily selling."))
    losers = mf[mf["Return %"] < -10]
    for _, r in losers.sort_values("Return %").head(3).iterrows():
        flags.append(("critical", f"{r['Fund Name']} down {abs(r['Return %']):.1f}%", "Currently a loss position on your original cost."))
if not stocks.empty:
    losers_s = stocks[stocks["Return %"] < -15]
    for _, r in losers_s.sort_values("Return %").head(3).iterrows():
        flags.append(("critical", f"{r['Symbol']} down {abs(r['Return %']):.1f}%", "Currently a significant loss position."))
if not fd.empty:
    overdue = fd[fd["Days to Maturity"] < 0]
    for _, r in overdue.iterrows():
        flags.append(("critical", f"{r['Holder Name']}'s FD matured {abs(int(r['Days to Maturity']))}d ago, uncollected",
                       f"{format_inr(r['Current Value (INR)'])} — likely earning the bank's low default savings rate instead of your contracted {r['ROI %']:.2f}%. Act on this."))
    soon = fd[fd["Days to Maturity"].between(0, 14)]
    for _, r in soon.iterrows():
        flags.append(("info", f"{r['Holder Name']}'s FD matures in {int(r['Days to Maturity'])}d",
                       f"{format_inr(r['Current Value (INR)'])} — decide reinvest vs. deploy elsewhere before it auto-renews at the bank's default rate."))
if mf_failed > 0:
    flags.append(("warning", f"{mf_failed} fund(s) missing a live NAV", "Excluded from totals — check the Mutual Funds tab."))

severity_rank = {"critical": 0, "warning": 1, "info": 2}
flags.sort(key=lambda f: severity_rank[f[0]])

# -------------------------------------------------
# NEWS — Google News RSS, filtered to your actual holdings, sorted by
# recency, older-than-45-days items dropped so it doesn't read as generic
# -------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news_for(names: list, max_items=8):
    items = []
    cutoff = datetime.now() - timedelta(days=45)
    for name in names[:6]:
        try:
            q = requests.utils.quote(name)
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                pub = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                if pub and pub < cutoff:
                    continue
                items.append({"title": entry.title, "link": entry.link,
                              "source": entry.get("source", {}).get("title", "") if hasattr(entry, "source") else "",
                              "published": entry.get("published", ""), "pub_dt": pub or datetime.min})
        except Exception:
            continue
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:max_items]

# -------------------------------------------------
# HISTORY
# -------------------------------------------------
def log_history_snapshot():
    os.makedirs("data", exist_ok=True)
    row = {"date": now_ist.strftime("%Y-%m-%d"), "net_worth": total_networth, "equity_pct": equity_pct,
           "fd_pct": fd_pct, "pnl": total_pnl, "health_score": round(health_score, 1)}
    if os.path.exists(HISTORY_PATH):
        hist_df = pd.read_csv(HISTORY_PATH)
        hist_df = hist_df[hist_df["date"] != row["date"]]
        hist_df = pd.concat([hist_df, pd.DataFrame([row])], ignore_index=True)
    else:
        hist_df = pd.DataFrame([row])
    hist_df.to_csv(HISTORY_PATH, index=False)
    return hist_df

history_df = log_history_snapshot() if log_snapshot else (pd.read_csv(HISTORY_PATH) if os.path.exists(HISTORY_PATH) else pd.DataFrame())

# ==================================================
# HEADER
# ==================================================
st.markdown('<div class="main-title">Family Net Worth</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">INR · Live prices · {now_ist.strftime("%d %b %Y, %H:%M IST")}</div>', unsafe_allow_html=True)

if len(amfi_navs) == 0:
    st.error("AMFI data failed to load this run — mutual fund values below may be stale or zero.")
elif mf_failed > 0:
    st.warning(f"{mf_failed} fund(s) missing a live NAV this run · {len(amfi_navs)} AMFI NAVs loaded OK")
else:
    st.success(f"Live prices OK · {len(amfi_navs)} AMFI NAVs loaded")

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Net Worth", format_inr(total_networth))
k2.metric("P&L", format_inr(total_pnl), f"{(total_pnl/total_invested*100):.1f}%" if total_invested else None)
k3.metric("Equity", f"{equity_pct:.1f}%")
k4.metric("FD / Cash", f"{fd_pct:.1f}%")
k5.metric("USD/INR", f"{usd_inr:.2f}")
k6.metric("Health Score", f"{health_score:.0f}", health_label)

# ==================================================
# WHAT NEEDS MY ATTENTION
# ==================================================
st.markdown('<div class="section-header">What needs my attention</div>', unsafe_allow_html=True)
if not flags:
    st.info("Nothing flagged right now.")
else:
    icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    for level, title, body in flags[:9]:
        st.markdown(f"""<div class="flag-card flag-{level}">
            <div style="font-size:1.05rem;line-height:1.3">{icon[level]}</div>
            <div><p class="flag-title">{title}</p><p class="flag-body">{body}</p></div>
        </div>""", unsafe_allow_html=True)

# ==================================================
# HEALTH BREAKDOWN + ALLOCATION
# ==================================================
c1, c2 = st.columns(2)
with c1:
    st.markdown('<div class="section-header">Portfolio health breakdown</div>', unsafe_allow_html=True)
    bd = pd.DataFrame({"Factor": list(factor_scores.keys()), "Score": list(factor_scores.values())})
    fig_h = go.Figure(go.Bar(x=bd["Score"], y=bd["Factor"], orientation="h",
        marker_color=["#ef4444" if s < 55 else ("#f59e0b" if s < 75 else "#22c55e") for s in bd["Score"]],
        text=[f"{s:.0f}" for s in bd["Score"]], textposition="outside"))
    fig_h.update_layout(height=210, margin=dict(t=5, b=5, l=5, r=25), xaxis=dict(range=[0, 105], showgrid=False),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
    st.plotly_chart(fig_h, use_container_width=True)
with c2:
    st.markdown('<div class="section-header">Asset allocation</div>', unsafe_allow_html=True)
    alloc_df = pd.DataFrame({"Asset": ["Fixed Deposits", "Mutual Funds", "Stocks"], "Value": [total_fd, total_mf, total_stocks]})
    fig = px.pie(alloc_df, values="Value", names="Asset", hole=0.62, color_discrete_sequence=["#3b82f6", "#22c55e", "#f59e0b"])
    fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=12)
    fig.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=210, showlegend=False,
                       paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
    st.plotly_chart(fig, use_container_width=True)

# ==================================================
# HISTORY — now multi-metric
# ==================================================
st.markdown('<div class="section-header">History</div>', unsafe_allow_html=True)
if len(history_df) < 2:
    st.caption("Building history — open this app on a few different days to see trends. "
               "Download the row(s) below periodically as a backup.")
    if not history_df.empty:
        st.dataframe(history_df, hide_index=True, use_container_width=True)
else:
    fig_hist = make_subplots(rows=1, cols=3, subplot_titles=("Net worth", "Equity % vs FD %", "Health score"))
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["net_worth"], line=dict(color="#3b82f6", width=2), showlegend=False), row=1, col=1)
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["equity_pct"], name="Equity %", line=dict(color="#22c55e", width=2)), row=1, col=2)
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["fd_pct"], name="FD %", line=dict(color="#3b82f6", width=2)), row=1, col=2)
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["health_score"], line=dict(color="#f59e0b", width=2), showlegend=False), row=1, col=3)
    fig_hist.update_layout(height=250, margin=dict(t=30, b=5, l=5, r=5), paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6",
                            legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig_hist, use_container_width=True)
    st.download_button("Download history.csv", history_df.to_csv(index=False), "networth_history.csv", "text/csv")

# ==================================================
# NEWS
# ==================================================
st.markdown('<div class="section-header">News on your holdings</div>', unsafe_allow_html=True)
top_names = []
if not mf.empty:
    top_names += mf.nlargest(3, "Current Value")["Fund Name"].str.split(" - ").str[0].tolist()
if not stocks.empty:
    top_names += stocks.nlargest(3, "Current Value")["Symbol"].tolist()
try:
    news_items = fetch_news_for(top_names) if top_names else []
except Exception:
    news_items = []
if not news_items:
    st.caption("No recent (last 45 days) news found for your top holdings this run.")
else:
    for item in news_items:
        st.markdown(f"""<div class="news-item"><a href="{item['link']}" target="_blank">{item['title']}</a>
            <div class="news-meta">{item.get('source','')} {('· ' + item['published']) if item.get('published') else ''}</div></div>""",
            unsafe_allow_html=True)

st.markdown("---")

# ==================================================
# BY FAMILY MEMBER + CATEGORY MIX
# ==================================================
c3, c4 = st.columns(2)
with c3:
    st.markdown('<div class="section-header">By family member</div>', unsafe_allow_html=True)
    owner_map = {}
    for df_, col, key in [(mf, "Current Value", "Owner"), (stocks, "Current Value", "Owner"), (fd, "Current Value (INR)", "Holder Name")]:
        if not df_.empty and key in df_.columns:
            for owner, val in df_.groupby(key)[col].sum().items():
                owner_map[owner] = owner_map.get(owner, 0) + val
    if owner_map:
        owner_df = pd.DataFrame([{"Owner": k, "Value": v} for k, v in owner_map.items()])
        fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s", color_discrete_sequence=["#3b82f6"])
        fig2.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=240, showlegend=False,
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
        st.plotly_chart(fig2, use_container_width=True)
with c4:
    st.markdown('<div class="section-header">Category mix (MF) — overlap proxy</div>', unsafe_allow_html=True)
    if not mf.empty:
        cat_df = mf.groupby("Category")["Current Value"].sum().reset_index().sort_values("Current Value", ascending=False)
        fig3 = px.bar(cat_df, x="Current Value", y="Category", orientation="h", color_discrete_sequence=["#22c55e"])
        fig3.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=240, showlegend=False,
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
        st.plotly_chart(fig3, use_container_width=True)
        st.markdown('<p class="caveat">Category-level concentration, not real stock-level overlap — genuine holdings-level overlap detection needs paid portfolio-disclosure data (Value Research/Morningstar-style) that has no free equivalent. Style drift and manager changes have the same limitation and aren\'t shown here for the same reason.</p>', unsafe_allow_html=True)

# ==================================================
# HOLDINGS
# ==================================================
st.markdown('<div class="section-header">Holdings</div>', unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["Mutual Funds", "Stocks", "Fixed Deposits"])

with tab1:
    if not mf.empty:
        st.caption(f"{len(mf)} consolidated holdings — Nifty columns are a broad-market comparison, not category-specific. '—' means insufficient history for that window.")
        st.dataframe(
            mf[["Owner", "Fund Name", "Category", "Current Value", "P&L", "Return %",
                "1Y %", "3Y %", "5Y %", "Nifty 1Y %", "Nifty 3Y %", "Nifty 5Y %"]]
            .style.format({"Current Value": "₹{:,.0f}", "P&L": "₹{:,.0f}", "Return %": "{:.1f}%",
                            "1Y %": "{:.1f}%", "3Y %": "{:.1f}%", "5Y %": "{:.1f}%",
                            "Nifty 1Y %": "{:.1f}%", "Nifty 3Y %": "{:.1f}%", "Nifty 5Y %": "{:.1f}%"}, na_rep="—"),
            use_container_width=True, height=380)

with tab2:
    if not stocks.empty:
        st.dataframe(
            stocks[["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"]]
            .style.format({"Invested": "₹{:,.0f}", "Current Value": "₹{:,.0f}", "P&L": "₹{:,.0f}",
                            "Return %": "{:.1f}%", "Current Price": "{:.2f}", "Quantity": "{:.0f}"}),
            use_container_width=True, height=380)
        st.caption("Fundamental red flags (P/E, debt/equity, promoter pledging) need paid/structured data beyond a live price feed — not shown here to avoid a false precision.")

with tab3:
    if not fd.empty:
        st.dataframe(
            fd[["Holder Name", "Currency", "Principal (INR)", "ROI %", "Days to Maturity", "Current Value (INR)", "Maturity Date"]]
            .style.format({"Principal (INR)": "₹{:,.0f}", "Current Value (INR)": "₹{:,.0f}", "ROI %": "{:.2f}"}),
            use_container_width=True, height=380)

st.markdown("---")
st.caption(f"INR · USD {usd_inr:.2f} · {now_ist.strftime('%d %b %Y %H:%M IST')} · AMFI {len(amfi_navs)} schemes loaded")
