import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime
import pytz
import plotly.express as px

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Family Net Worth",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------
# TIMEZONE
# -------------------------------------------------
IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)

# -------------------------------------------------
# DARK MODE + TIGHTER CSS
# -------------------------------------------------
st.markdown("""
<style>
    .stApp {
        background-color: #0f172a;
        color: #e2e8f0;
    }
    section[data-testid="stSidebar"] {
        background-color: #1e293b !important;
    }
    .main-title {
        font-size: 1.75rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 0.85rem;
        margin-bottom: 1.1rem;
    }
    .section-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #f1f5f9;
        margin: 1.3rem 0 0.5rem 0;
    }
    div[data-testid="stMetric"] {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 12px 14px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
        font-weight: 650;
        color: #f8fafc !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
    }
    .stDataFrame {
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
@st.cache_data(ttl=3600)
def get_amfi_nav_dict():
    try:
        url = "https://www.amfiindia.com/spages/NAVAll.txt"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        nav_dict = {}
        for line in r.text.splitlines():
            parts = line.split(";")
            if len(parts) >= 5:
                isin_growth = parts[1].strip()
                isin_div = parts[2].strip()
                try:
                    nav = float(parts[4].strip())
                except:
                    continue
                if isin_growth and len(isin_growth) > 8:
                    nav_dict[isin_growth] = nav
                if isin_div and len(isin_div) > 8:
                    nav_dict[isin_div] = nav
        return nav_dict
    except:
        return {}

@st.cache_data(ttl=300)
def get_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=8)
        return float(r.json()["rates"]["INR"])
    except:
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
    except:
        pass
    return None

def safe_float(val, default=0.0):
    try:
        v = pd.to_numeric(val, errors="coerce")
        return default if pd.isna(v) else float(v)
    except:
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
        except:
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
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    uploaded = st.file_uploader("Upload new Excel (optional)", type=["xlsx", "xls"])
    if st.button("🔄 Force Recalculate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption("Sources: AMFI · Yahoo Finance · Frankfurter")
    st.caption(f"IST: {now_ist.strftime('%d %b %Y, %H:%M')}")

# -------------------------------------------------
# LOAD
# -------------------------------------------------
fd_raw, mf_raw, stocks_raw = load_data(uploaded)
usd_inr = get_usd_inr()
amfi_navs = get_amfi_nav_dict()

# -------------------------------------------------
# PROCESS MUTUAL FUNDS (AGGREGATED)
# -------------------------------------------------
mf_txns = []
for _, row in mf_raw.iterrows():
    try:
        isin = str(row.get("ISIN", "") or "").strip()
        owner = str(row.get("Owner", "") or "").strip()
        fund_name = str(row.get("Fund Name", "") or "").strip()
        units = safe_float(row.get("Units"))
        invested = safe_float(row.get("Invested Amount", row.get("Invested")))
        if units <= 0 or not isin:
            continue
        mf_txns.append({"Owner": owner, "ISIN": isin, "Fund Name": fund_name, "Units": units, "Invested": invested})
    except:
        continue

mf_txns_df = pd.DataFrame(mf_txns)
if not mf_txns_df.empty:
    mf_agg = mf_txns_df.groupby(["Owner", "ISIN", "Fund Name"], as_index=False).agg({"Units": "sum", "Invested": "sum"})
else:
    mf_agg = pd.DataFrame(columns=["Owner", "ISIN", "Fund Name", "Units", "Invested"])

mf_rows = []
mf_failed = 0
for _, row in mf_agg.iterrows():
    try:
        isin = row["ISIN"]
        units = row["Units"]
        invested = row["Invested"]
        nav = amfi_navs.get(isin, None)
        if nav is None:
            mf_failed += 1
            nav = 0.0
        current_value = units * nav
        pnl = current_value - invested
        ret = (pnl / invested * 100) if invested > 0 else 0.0
        mf_rows.append({
            "Owner": row["Owner"], "ISIN": isin, "Fund Name": row["Fund Name"][:42],
            "Units": round(units, 3), "Invested": invested, "Current NAV": nav,
            "Current Value": current_value, "P&L": pnl, "Return %": ret
        })
    except:
        mf_failed += 1
mf = pd.DataFrame(mf_rows)

# -------------------------------------------------
# PROCESS STOCKS
# -------------------------------------------------
stock_rows = []
stock_failed = 0
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
                stock_failed += 1
                price = safe_float(row.get("Purchase Price", row.get("Avg Buy Price")))
        current_value = qty * price
        pnl = current_value - invested
        ret = (pnl / invested * 100) if invested > 0 else 0.0
        stock_rows.append({
            "Owner": str(row.get("Owner", "") or ""), "Symbol": symbol, "Quantity": qty,
            "Invested": invested, "Current Price": price, "Current Value": current_value,
            "P&L": pnl, "Return %": ret
        })
    except:
        stock_failed += 1
stocks = pd.DataFrame(stock_rows)

# -------------------------------------------------
# PROCESS FIXED DEPOSITS
# -------------------------------------------------
fd_rows = []
today = now_ist.date()
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
        try:
            mat_date = pd.to_datetime(row.get("Maturity Date"), errors="coerce")
            dep_date = pd.to_datetime(row.get("Deposit Date"), errors="coerce")
        except:
            mat_date = pd.NaT
            dep_date = pd.NaT
        days_to_mat = (mat_date.date() - today).days if pd.notna(mat_date) else None
        days_elapsed = (today - dep_date.date()).days if pd.notna(dep_date) else 0
        roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))
        accrued = principal * (roi / 100) * (max(days_elapsed, 0) / 365)
        current_value_original = principal + accrued
        if currency == "USD":
            current_value_inr = current_value_original * usd_inr
            principal_inr = principal * usd_inr
        else:
            current_value_inr = current_value_original
            principal_inr = principal
        fd_rows.append({
            "Holder Name": holder, "Account Number": account, "Currency": currency,
            "Principal (Original)": round(principal, 2), "Principal (INR)": round(principal_inr, 0),
            "ROI %": roi, "Days to Maturity": days_to_mat, "Accrued Interest": round(accrued, 0),
            "Current Value (Original)": round(current_value_original, 0),
            "Current Value (INR)": round(current_value_inr, 0),
            "Maturity Date": mat_date.strftime("%Y-%m-%d") if pd.notna(mat_date) else ""
        })
    except:
        continue
fd = pd.DataFrame(fd_rows)

# -------------------------------------------------
# AGGREGATES
# -------------------------------------------------
total_mf = mf["Current Value"].sum() if not mf.empty else 0
total_stocks = stocks["Current Value"].sum() if not stocks.empty else 0
total_fd = fd["Current Value (INR)"].sum() if not fd.empty else 0
total_networth = total_mf + total_stocks + total_fd
total_invested = (mf["Invested"].sum() if not mf.empty else 0) + (stocks["Invested"].sum() if not stocks.empty else 0) + (fd["Principal (INR)"].sum() if not fd.empty else 0)
total_pnl = total_networth - total_invested
equity_pct = ((total_mf + total_stocks) / total_networth * 100) if total_networth else 0
fd_pct = (total_fd / total_networth * 100) if total_networth else 0

# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.markdown('<div class="main-title">Family Net Worth Dashboard</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">All values in INR · Live prices · {now_ist.strftime("%d %b %Y, %H:%M IST")}</div>', unsafe_allow_html=True)

if len(amfi_navs) == 0:
    st.error("AMFI NAV data could not be loaded.")
elif mf_failed > 0:
    st.warning(f"{mf_failed} mutual funds missing NAV · {len(amfi_navs)} AMFI NAVs loaded")
else:
    st.success(f"All live prices OK · {len(amfi_navs)} AMFI NAVs loaded")

# -------------------------------------------------
# TOP KPIs
# -------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Net Worth", format_inr(total_networth))
k2.metric("Unrealized P&L", format_inr(total_pnl), f"{(total_pnl/total_invested*100):.1f}%" if total_invested else None)
k3.metric("Equity Allocation", f"{equity_pct:.1f}%")
k4.metric("FD / Cash Drag", f"{fd_pct:.1f}%")
k5.metric("USD / INR", f"{usd_inr:.2f}")

st.markdown("---")

# -------------------------------------------------
# CHARTS
# -------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    st.markdown('<div class="section-header">Asset Allocation</div>', unsafe_allow_html=True)
    alloc_df = pd.DataFrame({"Asset": ["Fixed Deposits", "Mutual Funds", "Stocks"], "Value": [total_fd, total_mf, total_stocks]})
    fig = px.pie(alloc_df, values="Value", names="Asset", hole=0.45, color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b"])
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown('<div class="section-header">Net Worth by Family Member</div>', unsafe_allow_html=True)
    owner_map = {}
    for df, col, key in [(mf, "Current Value", "Owner"), (stocks, "Current Value", "Owner"), (fd, "Current Value (INR)", "Holder Name")]:
        if not df.empty and key in df.columns:
            for owner, val in df.groupby(key)[col].sum().items():
                owner_map[owner] = owner_map.get(owner, 0) + val
    if owner_map:
        owner_df = pd.DataFrame([{"Owner": k, "Value": v} for k, v in owner_map.items()])
        fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s", color_discrete_sequence=["#3b82f6"])
        fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
        st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------
# KEY INSIGHTS - STAGE 1
# -------------------------------------------------
st.markdown('<div class="section-header">Key Insights</div>', unsafe_allow_html=True)

# FD Maturity Ladder
st.markdown("**📅 FD Maturity Ladder**")
if not fd.empty and "Days to Maturity" in fd.columns:
    ladder = {
        "Next 7 days": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 7)]["Principal (INR)"].sum(),
        "Next 30 days": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 30)]["Principal (INR)"].sum(),
        "Next 90 days": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 90)]["Principal (INR)"].sum(),
        "Next 1 year": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 365)]["Principal (INR)"].sum(),
    }
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Next 7 days", format_inr(ladder["Next 7 days"]))
    l2.metric("Next 30 days", format_inr(ladder["Next 30 days"]))
    l3.metric("Next 90 days", format_inr(ladder["Next 90 days"]))
    l4.metric("Next 1 year", format_inr(ladder["Next 1 year"]))
else:
    st.info("No FD maturity data")

st.markdown("")

# Three columns for insights
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**📅 Upcoming FDs (90 days)**")
    if not fd.empty and "Days to Maturity" in fd.columns:
        upcoming = fd[(fd["Days to Maturity"].notna()) & (fd["Days to Maturity"] <= 90) & (fd["Days to Maturity"] >= 0)].sort_values("Days to Maturity")
        if not upcoming.empty:
            st.dataframe(upcoming[["Holder Name", "Principal (INR)", "Days to Maturity"]].style.format({"Principal (INR)": "₹{:,.0f}"}), use_container_width=True, height=180)
        else:
            st.info("None")
    else:
        st.info("No data")

with col2:
    st.markdown("**🏆 Top MFs by Value**")
    if not mf.empty:
        top_val = mf.nlargest(5, "Current Value")[["Fund Name", "Current Value", "Return %"]]
        st.dataframe(top_val.style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=180)
    else:
        st.info("No data")

with col3:
    st.markdown("**📈 Top MFs by Return %**")
    if not mf.empty:
        top_ret = mf.nlargest(5, "Return %")[["Fund Name", "Current Value", "Return %"]]
        st.dataframe(top_ret.style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=180)
    else:
        st.info("No data")

# Second row of insights
col4, col5 = st.columns(2)

with col4:
    st.markdown("**📊 Top Stocks by Value**")
    if not stocks.empty:
        top_s_val = stocks.nlargest(5, "Current Value")[["Symbol", "Current Value", "Return %"]]
        st.dataframe(top_s_val.style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=180)
    else:
        st.info("No data")

with col5:
    st.markdown("**🚀 Top Stocks by Return %**")
    if not stocks.empty:
        top_s_ret = stocks.nlargest(5, "Return %")[["Symbol", "Current Value", "Return %"]]
        st.dataframe(top_s_ret.style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=180)
    else:
        st.info("No data")

# -------------------------------------------------
# FULL HOLDINGS
# -------------------------------------------------
st.markdown('<div class="section-header">Full Holdings Detail</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Mutual Funds", "Stocks", "Fixed Deposits"])

with tab1:
    if not mf.empty:
        st.caption(f"Showing {len(mf)} consolidated holdings · AMFI NAVs used")
        st.dataframe(mf.style.format({
            "Invested": "₹{:,.0f}", "Current Value": "₹{:,.0f}", "P&L": "₹{:,.0f}",
            "Return %": "{:.1f}%", "Current NAV": "{:.2f}", "Units": "{:.3f}"
        }), use_container_width=True, height=380)
    else:
        st.info("No mutual fund data")

with tab2:
    if not stocks.empty:
        st.dataframe(stocks.style.format({
            "Invested": "₹{:,.0f}", "Current Value": "₹{:,.0f}", "P&L": "₹{:,.0f}",
            "Return %": "{:.1f}%", "Current Price": "{:.2f}", "Quantity": "{:.0f}"
        }), use_container_width=True, height=380)
    else:
        st.info("No stock data")

with tab3:
    if not fd.empty:
        st.dataframe(fd.style.format({
            "Principal (Original)": "{:,.2f}", "Principal (INR)": "₹{:,.0f}",
            "Accrued Interest": "{:,.0f}", "Current Value (Original)": "{:,.0f}",
            "Current Value (INR)": "₹{:,.0f}", "ROI %": "{:.2f}"
        }), use_container_width=True, height=380)
    else:
        st.info("No fixed deposit data")

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.caption(f"All figures in INR · USD @ {usd_inr:.2f} · IST {now_ist.strftime('%d %b %Y %H:%M')} · AMFI: {len(amfi_navs)} · Personal use only")
