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
# HIGH QUALITY DARK THEME
# -------------------------------------------------
st.markdown("""
<style>
    /* Base */
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #111827 !important;
        border-right: 1px solid #1f2937;
    }
    
    /* Titles */
    .main-title {
        font-size: 1.65rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 0.15rem;
        letter-spacing: -0.02em;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 0.82rem;
        margin-bottom: 1.2rem;
    }
    .section-header {
        font-size: 0.95rem;
        font-weight: 600;
        color: #f1f5f9;
        margin: 1.5rem 0 0.7rem 0;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
        font-weight: 650;
        color: #f8fafc !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 0.78rem !important;
    }
    
    /* Tabs - better contrast */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #111827;
        gap: 4px;
        border-radius: 8px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #94a3b8 !important;
        border-radius: 6px;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        font-weight: 600;
    }
    
    /* Dataframe improvements */
    .stDataFrame {
        border: 1px solid #1f2937;
        border-radius: 8px;
    }
    
    /* General text */
    p, span, label, .stMarkdown {
        color: #e2e8f0 !important;
    }
    
    /* Reduce default padding a bit */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
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
    st.markdown("### Controls")
    uploaded = st.file_uploader("Upload new Excel", type=["xlsx", "xls"])
    if st.button("Force Recalculate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption("AMFI · Yahoo Finance · Frankfurter")
    st.caption(f"IST {now_ist.strftime('%d %b %Y, %H:%M')}")

# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------
fd_raw, mf_raw, stocks_raw = load_data(uploaded)
usd_inr = get_usd_inr()
amfi_navs = get_amfi_nav_dict()

# -------------------------------------------------
# PROCESS MF
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
            "Owner": row["Owner"], "ISIN": isin, "Fund Name": row["Fund Name"][:40],
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
        stock_rows.append({
            "Owner": str(row.get("Owner", "") or ""), "Symbol": symbol, "Quantity": qty,
            "Invested": invested, "Current Price": price, "Current Value": current_value,
            "P&L": pnl, "Return %": ret
        })
    except:
        continue
stocks = pd.DataFrame(stock_rows)

# -------------------------------------------------
# PROCESS FD
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
# AGGREGATES + HEALTH
# -------------------------------------------------
total_mf = mf["Current Value"].sum() if not mf.empty else 0
total_stocks = stocks["Current Value"].sum() if not stocks.empty else 0
total_fd = fd["Current Value (INR)"].sum() if not fd.empty else 0
total_networth = total_mf + total_stocks + total_fd
total_invested = (mf["Invested"].sum() if not mf.empty else 0) + (stocks["Invested"].sum() if not stocks.empty else 0) + (fd["Principal (INR)"].sum() if not fd.empty else 0)
total_pnl = total_networth - total_invested
equity_pct = ((total_mf + total_stocks) / total_networth * 100) if total_networth else 0
fd_pct = (total_fd / total_networth * 100) if total_networth else 0

# Health Score
score = 70
if equity_pct < 15: score -= 8
elif equity_pct > 40: score -= 5
else: score += 5
if fd_pct > 75: score -= 10
elif fd_pct > 65: score -= 5
else: score += 3
top5_mf_pct = (mf.nlargest(5, "Current Value")["Current Value"].sum() / total_mf * 100) if not mf.empty and total_mf > 0 else 0
top5_stock_pct = (stocks.nlargest(5, "Current Value")["Current Value"].sum() / total_stocks * 100) if not stocks.empty and total_stocks > 0 else 0
if top5_mf_pct > 60: score -= 6
if top5_stock_pct > 50: score -= 5
score = max(0, min(100, score))
health_label = "🟢 Healthy" if score >= 80 else ("🟡 Adequate" if score >= 65 else "🔴 Needs Attention")
commentary = "Portfolio is heavily conservative (FD-dominated)." if fd_pct > 70 else ("Equity allocation is meaningful." if equity_pct > 35 else "Balanced between safety and growth.")

# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.markdown('<div class="main-title">Family Net Worth</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">INR · Live prices · {now_ist.strftime("%d %b %Y, %H:%M IST")}</div>', unsafe_allow_html=True)

if len(amfi_navs) == 0:
    st.error("AMFI data failed to load")
elif mf_failed > 0:
    st.warning(f"{mf_failed} MFs missing NAV · {len(amfi_navs)} AMFI NAVs")
else:
    st.success(f"Live prices OK · {len(amfi_navs)} AMFI NAVs")

# -------------------------------------------------
# KPIs
# -------------------------------------------------
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Net Worth", format_inr(total_networth))
k2.metric("P&L", format_inr(total_pnl), f"{(total_pnl/total_invested*100):.1f}%" if total_invested else None)
k3.metric("Equity", f"{equity_pct:.1f}%")
k4.metric("FD Drag", f"{fd_pct:.1f}%")
k5.metric("USD/INR", f"{usd_inr:.2f}")
k6.metric("Health", f"{score}", health_label)

st.caption(commentary)
st.markdown("---")

# -------------------------------------------------
# CHARTS
# -------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    st.markdown('<div class="section-header">Asset Allocation</div>', unsafe_allow_html=True)
    alloc_df = pd.DataFrame({"Asset": ["Fixed Deposits", "Mutual Funds", "Stocks"], "Value": [total_fd, total_mf, total_stocks]})
    fig = px.pie(alloc_df, values="Value", names="Asset", hole=0.5,
                 color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b"])
    fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=12)
    fig.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=260, showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown('<div class="section-header">By Family Member</div>', unsafe_allow_html=True)
    owner_map = {}
    for df, col, key in [(mf, "Current Value", "Owner"), (stocks, "Current Value", "Owner"), (fd, "Current Value (INR)", "Holder Name")]:
        if not df.empty and key in df.columns:
            for owner, val in df.groupby(key)[col].sum().items():
                owner_map[owner] = owner_map.get(owner, 0) + val
    if owner_map:
        owner_df = pd.DataFrame([{"Owner": k, "Value": v} for k, v in owner_map.items()])
        fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s", color_discrete_sequence=["#3b82f6"])
        fig2.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=260, showlegend=False,
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
        st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------
# KEY INSIGHTS
# -------------------------------------------------
st.markdown('<div class="section-header">Key Insights</div>', unsafe_allow_html=True)

# FD Ladder
st.markdown("**FD Maturity Ladder**")
if not fd.empty and "Days to Maturity" in fd.columns:
    ladder = {
        "7 days": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 7)]["Principal (INR)"].sum(),
        "30 days": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 30)]["Principal (INR)"].sum(),
        "90 days": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 90)]["Principal (INR)"].sum(),
        "1 year": fd[(fd["Days to Maturity"] >= 0) & (fd["Days to Maturity"] <= 365)]["Principal (INR)"].sum(),
    }
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Next 7d", format_inr(ladder["7 days"]))
    l2.metric("Next 30d", format_inr(ladder["30 days"]))
    l3.metric("Next 90d", format_inr(ladder["90 days"]))
    l4.metric("Next 1Y", format_inr(ladder["1 year"]))

# Concentration
st.markdown("**Concentration**")
cc1, cc2, cc3 = st.columns(3)
cc1.metric("Top 5 MFs", f"{top5_mf_pct:.1f}%")
cc2.metric("Top 5 Stocks", f"{top5_stock_pct:.1f}%")
cc3.metric("Equity %", f"{equity_pct:.1f}%")

# Tables row
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Upcoming FDs**")
    if not fd.empty:
        upcoming = fd[(fd["Days to Maturity"].notna()) & (fd["Days to Maturity"] <= 90) & (fd["Days to Maturity"] >= 0)].sort_values("Days to Maturity")
        if not upcoming.empty:
            st.dataframe(upcoming[["Holder Name", "Principal (INR)", "Days to Maturity"]].head(5).style.format({"Principal (INR)": "₹{:,.0f}"}), use_container_width=True, height=160)
        else:
            st.info("None soon")
with col2:
    st.markdown("**Top MFs by Value**")
    if not mf.empty:
        st.dataframe(mf.nlargest(5, "Current Value")[["Fund Name", "Current Value", "Return %"]].style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=160)
with col3:
    st.markdown("**Top MFs by Return**")
    if not mf.empty:
        st.dataframe(mf.nlargest(5, "Return %")[["Fund Name", "Current Value", "Return %"]].style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=160)

col4, col5 = st.columns(2)
with col4:
    st.markdown("**Top Stocks by Value**")
    if not stocks.empty:
        st.dataframe(stocks.nlargest(5, "Current Value")[["Symbol", "Current Value", "Return %"]].style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=160)
with col5:
    st.markdown("**Top Stocks by Return**")
    if not stocks.empty:
        st.dataframe(stocks.nlargest(5, "Return %")[["Symbol", "Current Value", "Return %"]].style.format({"Current Value": "₹{:,.0f}", "Return %": "{:.1f}%"}), use_container_width=True, height=160)

# -------------------------------------------------
# FULL HOLDINGS
# -------------------------------------------------
st.markdown('<div class="section-header">Holdings</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Mutual Funds", "Stocks", "Fixed Deposits"])

with tab1:
    if not mf.empty:
        st.caption(f"{len(mf)} consolidated holdings")
        st.dataframe(
            mf[["Owner", "Fund Name", "Units", "Invested", "Current NAV", "Current Value", "P&L", "Return %"]]
            .style.format({
                "Invested": "₹{:,.0f}", "Current Value": "₹{:,.0f}", "P&L": "₹{:,.0f}",
                "Return %": "{:.1f}%", "Current NAV": "{:.2f}", "Units": "{:.2f}"
            }),
            use_container_width=True, height=360
        )

with tab2:
    if not stocks.empty:
        st.dataframe(
            stocks[["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"]]
            .style.format({
                "Invested": "₹{:,.0f}", "Current Value": "₹{:,.0f}", "P&L": "₹{:,.0f}",
                "Return %": "{:.1f}%", "Current Price": "{:.2f}", "Quantity": "{:.0f}"
            }),
            use_container_width=True, height=360
        )

with tab3:
    if not fd.empty:
        st.dataframe(
            fd[["Holder Name", "Currency", "Principal (INR)", "ROI %", "Days to Maturity", "Current Value (INR)", "Maturity Date"]]
            .style.format({
                "Principal (INR)": "₹{:,.0f}", "Current Value (INR)": "₹{:,.0f}", "ROI %": "{:.2f}"
            }),
            use_container_width=True, height=360
        )

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.caption(f"INR · USD {usd_inr:.2f} · {now_ist.strftime('%d %b %Y %H:%M IST')} · AMFI {len(amfi_navs)}")
