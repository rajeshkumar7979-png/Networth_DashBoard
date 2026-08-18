import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Family Net Worth Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for cleaner look
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a365d;
        margin-bottom: 0.2rem;
    }
    .metric-card {
        background: #f8fafc;
        padding: 1rem 1.2rem;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
    }
    .stMetric > div {
        background-color: #ffffff;
        padding: 12px 16px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------
@st.cache_data(ttl=300)  # cache 5 minutes
def get_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=8)
        return r.json()["rates"]["INR"]
    except:
        return 95.5  # fallback

@st.cache_data(ttl=600)
def get_mf_nav(isin):
    try:
        # mfapi.in by ISIN is not direct; we use a simple search approach
        # For production we match via scheme code, but here we keep it simple
        url = f"https://api.mfapi.in/mf/search?q={isin}"
        r = requests.get(url, timeout=8)
        if r.status_code == 200 and r.json():
            code = r.json()[0]["schemeCode"]
            nav_r = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=8)
            data = nav_r.json()
            if "data" in data and len(data["data"]) > 0:
                return float(data["data"][0]["nav"]), data["data"][0]["date"]
    except:
        pass
    return None, None

@st.cache_data(ttl=300)
def get_stock_price(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except:
        pass
    return None

def load_data(uploaded_file=None):
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
    else:
        try:
            xls = pd.ExcelFile("data/Networth_Raw_Data.xlsx")
        except:
            st.error("Could not find data/Networth_Raw_Data.xlsx. Please upload your file.")
            st.stop()

    # Read sheets (flexible names)
    sheets = {s.lower(): s for s in xls.sheet_names}

    fd = pd.read_excel(xls, sheets.get("fd", list(xls.sheet_names)[0]) if "fd" in sheets else 0)
    mf = pd.read_excel(xls, sheets.get("mf", list(xls.sheet_names)[1]) if "mf" in sheets else 1)
    stocks = pd.read_excel(xls, sheets.get("stocks", list(xls.sheet_names)[2]) if "stocks" in sheets else 2)

    return fd, mf, stocks

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.title("⚙️ Controls")
    uploaded = st.file_uploader("Upload new raw data (Excel)", type=["xlsx", "xls"])
    
    if st.button("🔄 Force Recalculate Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption("Data sources: mfapi.in • Yahoo Finance • Frankfurter")
    st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}")

# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------
fd_df, mf_df, stocks_df = load_data(uploaded)

usd_inr = get_usd_inr()

# -------------------------------------------------
# PROCESS MUTUAL FUNDS
# -------------------------------------------------
mf_processed = []
mf_failed = 0

for _, row in mf_df.iterrows():
    isin = str(row.get("ISIN", "")).strip()
    units = float(row.get("Units", 0) or 0)
    invested = float(row.get("Invested Amount", 0) or row.get("Invested", 0) or 0)
    
    nav, nav_date = get_mf_nav(isin) if isin else (None, None)
    
    if nav is None:
        # fallback to any existing Current NAV column
        nav = float(row.get("Current NAV", 0) or 0)
        if nav == 0:
            mf_failed += 1
            nav = float(row.get("Purchase NAV", 0) or 0)
    
    current_value = units * nav if nav else 0
    pnl = current_value - invested
    ret = (pnl / invested * 100) if invested > 0 else 0

    mf_processed.append({
        "Owner": row.get("Owner", ""),
        "ISIN": isin,
        "Fund Name": row.get("Fund Name", ""),
        "Units": units,
        "Invested": invested,
        "Current NAV": nav,
        "NAV Date": nav_date,
        "Current Value": current_value,
        "P&L": pnl,
        "Return %": ret
    })

mf_final = pd.DataFrame(mf_processed)

# -------------------------------------------------
# PROCESS STOCKS
# -------------------------------------------------
stock_processed = []
stock_failed = 0

for _, row in stocks_df.iterrows():
    symbol = str(row.get("Symbol", row.get("Ticker / Symbol", ""))).strip().upper()
    qty = float(row.get("Quantity", 0) or 0)
    invested = float(row.get("Invested Amount", 0) or 0)
    
    price = get_stock_price(symbol) if symbol else None
    
    if price is None:
        price = float(row.get("Current Price", row.get("Current Price (CMP)", 0)) or 0)
        if price == 0:
            stock_failed += 1
            price = float(row.get("Purchase Price", row.get("Avg Buy Price", 0)) or 0)
    
    current_value = qty * price
    pnl = current_value - invested
    ret = (pnl / invested * 100) if invested > 0 else 0

    stock_processed.append({
        "Owner": row.get("Owner", ""),
        "Symbol": symbol,
        "Quantity": qty,
        "Invested": invested,
        "Current Price": price,
        "Current Value": current_value,
        "P&L": pnl,
        "Return %": ret
    })

stocks_final = pd.DataFrame(stock_processed)

# -------------------------------------------------
# PROCESS FDs (simple current value approximation)
# -------------------------------------------------
fd_processed = []
for _, row in fd_df.iterrows():
    principal = float(row.get("Principal Amount", 0) or 0)
    currency = str(row.get("Currency", "INR")).upper()
    maturity = row.get("Maturity Amount", principal)
    
    # Simple: use Principal as current for now (or maturity if closer)
    current = principal
    current_inr = current * usd_inr if currency == "USD" else current

    fd_processed.append({
        "Holder Name": row.get("Holder Name", ""),
        "Currency": currency,
        "Principal": principal,
        "Current Value (INR)": current_inr,
        "Maturity Date": row.get("Maturity Date", "")
    })

fd_final = pd.DataFrame(fd_processed)

# -------------------------------------------------
# AGGREGATES
# -------------------------------------------------
total_mf = mf_final["Current Value"].sum()
total_stocks = stocks_final["Current Value"].sum()
total_fd = fd_final["Current Value (INR)"].sum()

total_networth = total_mf + total_stocks + total_fd
total_invested = mf_final["Invested"].sum() + stocks_final["Invested"].sum() + fd_final["Principal"].sum()
total_pnl = total_networth - total_invested
equity_pct = ((total_mf + total_stocks) / total_networth * 100) if total_networth > 0 else 0

# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.markdown('<p class="main-header">Family Net Worth Dashboard</p>', unsafe_allow_html=True)
st.caption(f"Live prices • Last calculated: {datetime.now().strftime('%d %b %Y %H:%M IST')}")

# Data Quality Banner
if mf_failed > 0 or stock_failed > 0:
    st.warning(f"⚠️ Data Quality: {mf_failed} mutual funds and {stock_failed} stocks could not get a live price. Using fallback values.")
else:
    st.success("✅ All live prices fetched successfully")

# -------------------------------------------------
# TOP METRICS
# -------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Net Worth", f"₹{total_networth:,.0f}")
col2.metric("Total P&L", f"₹{total_pnl:,.0f}", f"{(total_pnl/total_invested*100):.1f}%" if total_invested else "0%")
col3.metric("Equity Allocation", f"{equity_pct:.1f}%")
col4.metric("USD/INR", f"{usd_inr:.2f}")
col5.metric("Total Invested", f"₹{total_invested:,.0f}")

st.markdown("---")

# -------------------------------------------------
# CHARTS
# -------------------------------------------------
c1, c2 = st.columns(2)

with c1:
    st.subheader("Asset Allocation")
    alloc = pd.DataFrame({
        "Asset": ["Fixed Deposits", "Mutual Funds", "Stocks"],
        "Value": [total_fd, total_mf, total_stocks]
    })
    fig = px.pie(alloc, values="Value", names="Asset", hole=0.45,
                 color_discrete_sequence=["#3182ce", "#38a169", "#d69e2e"])
    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=320)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Net Worth by Family Member")
    # Simple owner aggregation
    owner_data = []
    for owner in set(list(mf_final["Owner"]) + list(stocks_final["Owner"])):
        mf_val = mf_final[mf_final["Owner"] == owner]["Current Value"].sum()
        st_val = stocks_final[stocks_final["Owner"] == owner]["Current Value"].sum()
        owner_data.append({"Owner": owner, "Value": mf_val + st_val})
    
    owner_df = pd.DataFrame(owner_data)
    fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s",
                  color_discrete_sequence=["#2b6cb0"])
    fig2.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=320, showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------
# DETAILED TABLES
# -------------------------------------------------
st.markdown("---")
st.subheader("Full Holdings Detail")

tab1, tab2, tab3 = st.tabs(["Mutual Funds", "Stocks", "Fixed Deposits"])

with tab1:
    st.dataframe(
        mf_final.style.format({
            "Invested": "₹{:,.0f}",
            "Current Value": "₹{:,.0f}",
            "P&L": "₹{:,.0f}",
            "Return %": "{:.1f}%",
            "Current NAV": "{:.2f}"
        }),
        use_container_width=True,
        height=400
    )

with tab2:
    st.dataframe(
        stocks_final.style.format({
            "Invested": "₹{:,.0f}",
            "Current Value": "₹{:,.0f}",
            "P&L": "₹{:,.0f}",
            "Return %": "{:.1f}%",
            "Current Price": "{:.2f}"
        }),
        use_container_width=True,
        height=400
    )

with tab3:
    st.dataframe(fd_final, use_container_width=True, height=400)

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.caption("Built for personal use • Prices from mfapi.in, Yahoo Finance & Frankfurter • Not financial advice")
