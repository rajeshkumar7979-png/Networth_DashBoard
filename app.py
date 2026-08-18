import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

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
# MODERN CSS
# -------------------------------------------------
st.markdown("""
<style>
    /* Main header */
    .main-title {
        font-size: 1.9rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.15rem;
    }
    .sub-title {
        color: #64748b;
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.55rem !important;
        font-weight: 650;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.8rem;
        color: #64748b;
    }

    /* Section headers */
    .section-header {
        font-size: 1.15rem;
        font-weight: 600;
        color: #1e293b;
        margin: 1.8rem 0 0.8rem 0;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #f8fafc;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
@st.cache_data(ttl=300)
def get_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=8)
        return float(r.json()["rates"]["INR"])
    except:
        return 95.5

@st.cache_data(ttl=600)
def get_mf_nav(isin: str):
    if not isin or len(isin) < 8:
        return None, None
    try:
        r = requests.get(f"https://api.mfapi.in/mf/search?q={isin}", timeout=8)
        if r.status_code == 200 and r.json():
            code = r.json()[0]["schemeCode"]
            nav_r = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=8)
            data = nav_r.json()
            if data.get("data"):
                return float(data["data"][0]["nav"]), data["data"][0]["date"]
    except:
        pass
    return None, None

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

def load_data(uploaded_file=None):
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
    else:
        try:
            xls = pd.ExcelFile("data/Networth_Raw_Data.xlsx")
        except Exception as e:
            st.error("Could not load data/Networth_Raw_Data.xlsx. Please upload the file from the sidebar.")
            st.stop()

    # Flexible sheet detection
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
    st.caption("Sources: mfapi.in · Yahoo Finance · Frankfurter")
    st.caption(f"Refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}")

# -------------------------------------------------
# LOAD
# -------------------------------------------------
fd_raw, mf_raw, stocks_raw = load_data(uploaded)
usd_inr = get_usd_inr()

# -------------------------------------------------
# PROCESS MUTUAL FUNDS
# -------------------------------------------------
mf_rows = []
mf_failed = 0

for _, row in mf_raw.iterrows():
    try:
        isin = str(row.get("ISIN", "") or "").strip()
        units = safe_float(row.get("Units"))
        invested = safe_float(row.get("Invested Amount", row.get("Invested")))

        nav, nav_date = get_mf_nav(isin) if isin else (None, None)

        if nav is None:
            nav = safe_float(row.get("Current NAV"))
            if nav == 0:
                mf_failed += 1
                nav = safe_float(row.get("Purchase NAV"))

        current_value = units * nav
        pnl = current_value - invested
        ret = (pnl / invested * 100) if invested > 0 else 0.0

        mf_rows.append({
            "Owner": str(row.get("Owner", "") or ""),
            "ISIN": isin,
            "Fund Name": str(row.get("Fund Name", "") or ""),
            "Units": units,
            "Invested": invested,
            "Current NAV": nav,
            "NAV Date": nav_date or "",
            "Current Value": current_value,
            "P&L": pnl,
            "Return %": ret
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
            "Owner": str(row.get("Owner", "") or ""),
            "Symbol": symbol,
            "Quantity": qty,
            "Invested": invested,
            "Current Price": price,
            "Current Value": current_value,
            "P&L": pnl,
            "Return %": ret
        })
    except:
        stock_failed += 1

stocks = pd.DataFrame(stock_rows)

# -------------------------------------------------
# PROCESS FIXED DEPOSITS (CLEAN + ENHANCED)
# -------------------------------------------------
fd_rows = []
today = datetime.now().date()

for _, row in fd_raw.iterrows():
    try:
        holder = str(row.get("Holder Name", "") or "").strip()
        account = str(row.get("Account Number", "") or "").strip()
        principal = safe_float(row.get("Principal Amount"))

        # Skip summary / total / empty rows
        if (not holder or holder.lower() in ["nan", "nat", "none"] or
            principal <= 0 or
            "total" in holder.lower() or
            account in ["", "nan", "None"] and principal > 1000000):   # rough filter for totals
            continue

        currency = str(row.get("Currency", "INR") or "INR").upper().strip()
        if currency not in ["INR", "USD"]:
            currency = "INR"

        # Dates
        try:
            mat_date = pd.to_datetime(row.get("Maturity Date"), errors="coerce")
            dep_date = pd.to_datetime(row.get("Deposit Date"), errors="coerce")
        except:
            mat_date = pd.NaT
            dep_date = pd.NaT

        days_to_mat = (mat_date.date() - today).days if pd.notna(mat_date) else None
        days_elapsed = (today - dep_date.date()).days if pd.notna(dep_date) else 0

        roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))

        # Simple accrued interest (approximate)
        accrued = principal * (roi / 100) * (days_elapsed / 365) if days_elapsed > 0 else 0
        current_value = principal + accrued
        current_inr = current_value * usd_inr if currency == "USD" else current_value

        fd_rows.append({
            "Holder Name": holder,
            "Account Number": account,
            "Currency": currency,
            "Principal": principal,
            "ROI %": roi,
            "Days to Maturity": days_to_mat,
            "Accrued Interest": round(accrued, 0),
            "Current Value": round(current_value, 0),
            "Current Value (INR)": round(current_inr, 0),
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
total_invested = (mf["Invested"].sum() if not mf.empty else 0) + \
                 (stocks["Invested"].sum() if not stocks.empty else 0) + \
                 (fd["Principal"].sum() if not fd.empty else 0)
total_pnl = total_networth - total_invested
equity_pct = ((total_mf + total_stocks) / total_networth * 100) if total_networth else 0
fd_pct = (total_fd / total_networth * 100) if total_networth else 0

# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.markdown('<div class="main-title">Family Net Worth Dashboard</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">Live prices · Last calculated {datetime.now().strftime("%d %b %Y, %H:%M IST")}</div>', unsafe_allow_html=True)

if mf_failed or stock_failed:
    st.warning(f"Data quality note: {mf_failed} MF and {stock_failed} stocks used fallback prices.")
else:
    st.success("All live prices fetched successfully")

# -------------------------------------------------
# KPI ROW
# -------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Net Worth", f"₹{total_networth:,.0f}")
k2.metric("Unrealized P&L", f"₹{total_pnl:,.0f}", f"{(total_pnl/total_invested*100):.1f}%" if total_invested else None)
k3.metric("Equity Allocation", f"{equity_pct:.1f}%")
k4.metric("FD / Cash Drag", f"{fd_pct:.1f}%")
k5.metric("USD / INR", f"{usd_inr:.2f}")

st.markdown("---")

# -------------------------------------------------
# CHARTS
# -------------------------------------------------
left, right = st.columns(2)

with left:
    st.markdown('<div class="section-header">Asset Allocation</div>', unsafe_allow_html=True)
    alloc_df = pd.DataFrame({
        "Asset": ["Fixed Deposits", "Mutual Funds", "Stocks"],
        "Value": [total_fd, total_mf, total_stocks]
    })
    fig = px.pie(alloc_df, values="Value", names="Asset", hole=0.48,
                 color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b"])
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=340, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown('<div class="section-header">Net Worth by Family Member</div>', unsafe_allow_html=True)
    owner_map = {}
    for df, col in [(mf, "Current Value"), (stocks, "Current Value"), (fd, "Current Value (INR)")]:
        if not df.empty and "Owner" in df.columns or "Holder Name" in df.columns:
            key = "Owner" if "Owner" in df.columns else "Holder Name"
            for owner, val in df.groupby(key)[col].sum().items():
                owner_map[owner] = owner_map.get(owner, 0) + val

    if owner_map:
        owner_df = pd.DataFrame([{"Owner": k, "Value": v} for k, v in owner_map.items()])
        fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s",
                      color_discrete_sequence=["#1e40af"])
        fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=340, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------
# DETAILED TABLES
# -------------------------------------------------
st.markdown('<div class="section-header">Full Holdings</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Mutual Funds", "Stocks", "Fixed Deposits"])

with tab1:
    if not mf.empty:
        st.dataframe(
            mf.style.format({
                "Invested": "₹{:,.0f}",
                "Current Value": "₹{:,.0f}",
                "P&L": "₹{:,.0f}",
                "Return %": "{:.1f}%",
                "Current NAV": "{:.2f}",
                "Units": "{:.3f}"
            }),
            use_container_width=True, height=420
        )
    else:
        st.info("No mutual fund data found")

with tab2:
    if not stocks.empty:
        st.dataframe(
            stocks.style.format({
                "Invested": "₹{:,.0f}",
                "Current Value": "₹{:,.0f}",
                "P&L": "₹{:,.0f}",
                "Return %": "{:.1f}%",
                "Current Price": "{:.2f}",
                "Quantity": "{:.0f}"
            }),
            use_container_width=True, height=420
        )
    else:
        st.info("No stock data found")

with tab3:
    if not fd.empty:
        st.dataframe(
            fd.style.format({
                "Principal": "₹{:,.0f}",
                "Accrued Interest": "₹{:,.0f}",
                "Current Value": "₹{:,.0f}",
                "Current Value (INR)": "₹{:,.0f}",
                "ROI %": "{:.2f}"
            }),
            use_container_width=True, height=420
        )
    else:
        st.info("No fixed deposit data found")

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.caption("Personal use only · Live data from mfapi.in, Yahoo Finance & Frankfurter · Not financial advice")
