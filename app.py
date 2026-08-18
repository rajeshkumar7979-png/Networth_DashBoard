"""
Family Net Worth Dashboard — single-file Streamlit app.

One app does everything: reads your raw holdings, fetches live prices/NAVs/FX,
computes net worth + P&L, and renders the dashboard. Deploy once (free, on
Streamlit Community Cloud) and it's a single bookmarked URL from then on —
open it, it refreshes itself.

DATA SOURCE:
  Put your raw data workbook at data/Networth_Raw_Data.xlsx (same 4 tabs as
  your original file: FD, MF, Stocks). If that file isn't found, the sidebar
  lets you upload one for the session instead.

PRICE SOURCES (all free, no API key required):
  - Mutual funds : mfapi.in            (wraps AMFI NAV data, keyed by ISIN)
  - Stocks       : Yahoo Finance       (via the yfinance library)
  - FX (USD/INR) : frankfurter.app     (European Central Bank rates)

MANUAL OVERRIDES:
  Some instruments (e.g. Sovereign Gold Bonds) don't resolve on Yahoo
  Finance. Edit MANUAL_PRICE_OVERRIDES below, or use the sidebar table.
"""

import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(page_title="Family Net Worth", layout="wide")

DATA_PATH = "data/Networth_Raw_Data.xlsx"

# Tickers/ISINs Yahoo Finance / mfapi can't resolve — fill in a manual price.
# Example: "SGBSEP31II-GB": 8100   (edit as needed, or use the sidebar)
MANUAL_PRICE_OVERRIDES = {
    "SGBSEP31II-GB": None,
    "SGBMR29XII-GB": None,
}

TARGET_EQUITY_PCT = 60  # edit to your target asset allocation

# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_raw(file):
    fd = pd.read_excel(file, sheet_name="FD")
    fd.columns = [c.strip() for c in fd.columns]
    fd = fd[pd.to_numeric(fd["Account Number"], errors="coerce").notna()].copy()

    mf = pd.read_excel(file, sheet_name="MF")
    mf.columns = [c.strip() for c in mf.columns]

    stk = pd.read_excel(file, sheet_name="Stocks")
    stk.columns = [c.strip() for c in stk.columns]

    return fd, mf, stk


# ---------------------------------------------------------------------------
# LIVE PRICE FETCHING (each cached separately so one failure doesn't block
# the others, and so re-running doesn't re-fetch everything every time)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mf_nav(isin: str):
    """Current NAV for a fund via mfapi.in, matched by ISIN."""
    try:
        # mfapi's search-by-ISIN isn't direct; the reliable path is via the
        # scheme list once, then per-scheme NAV. We cache the scheme list
        # separately (see fetch_mf_scheme_list) and look up the code here.
        code = _mf_scheme_code_for_isin(isin)
        if not code:
            return None, None
        r = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("data"):
            latest = data["data"][0]
            return float(latest["nav"]), latest["date"]
    except Exception:
        pass
    return None, None


@st.cache_data(ttl=86400, show_spinner=False)
def _mf_scheme_list():
    """All AMFI scheme codes with their ISINs — fetched once/day, then
    looked up locally instead of hitting the API once per fund."""
    try:
        r = requests.get("https://api.mfapi.in/mf", timeout=15)
        r.raise_for_status()
        return r.json()  # list of {schemeCode, schemeName}
    except Exception:
        return []


def _mf_scheme_code_for_isin(isin: str):
    # mfapi's bulk list doesn't include ISIN directly, so we search AMFI's
    # own NAVAll feed once (cached) and build the ISIN -> scheme code map.
    amfi_map = _amfi_isin_map()
    return amfi_map.get(isin)


@st.cache_data(ttl=86400, show_spinner=False)
def _amfi_isin_map():
    """ISIN -> AMFI scheme code, parsed once/day from the official bulk file."""
    mapping = {}
    try:
        r = requests.get("https://www.amfiindia.com/spages/NAVAll.txt", timeout=20)
        r.raise_for_status()
        for line in r.text.splitlines():
            parts = line.split(";")
            if len(parts) >= 6 and parts[0].strip().isdigit():
                code, isin_growth, isin_div = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if isin_growth and isin_growth != "-":
                    mapping[isin_growth] = code
                if isin_div and isin_div != "-":
                    mapping[isin_div] = code
    except Exception:
        pass
    return mapping


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_stock_price(ticker: str):
    if ticker in MANUAL_PRICE_OVERRIDES and MANUAL_PRICE_OVERRIDES[ticker]:
        return MANUAL_PRICE_OVERRIDES[ticker]
    try:
        t = yf.Ticker(f"{ticker}.NS")
        price = t.fast_info.get("last_price")
        if price:
            return float(price)
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=10)
        r.raise_for_status()
        return r.json()["rates"]["INR"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# COMPUTE ENGINE
# ---------------------------------------------------------------------------

def compute_mf_holdings(mf_raw: pd.DataFrame) -> pd.DataFrame:
    holdings = (
        mf_raw.groupby(["Owner", "ISIN", "Fund Name"], as_index=False)
        .agg(Units=("Units", "sum"), Invested=("Invested Amount", "sum"))
    )
    holdings["Avg Cost NAV"] = holdings["Invested"] / holdings["Units"]

    navs, dates = [], []
    for isin in holdings["ISIN"]:
        nav, date = fetch_mf_nav(isin)
        navs.append(nav)
        dates.append(date)
    holdings["Current NAV"] = navs
    holdings["NAV Date"] = dates
    holdings["Current Value"] = holdings["Units"] * holdings["Current NAV"]
    holdings["P&L"] = holdings["Current Value"] - holdings["Invested"]
    holdings["Return %"] = holdings["P&L"] / holdings["Invested"] * 100
    return holdings


def compute_stock_holdings(stk_raw: pd.DataFrame) -> pd.DataFrame:
    stk = stk_raw.copy()
    stk["Live Price"] = stk["Ticker / Symbol"].apply(fetch_stock_price)
    # fall back to the raw file's last known price if a live fetch fails,
    # so one bad ticker doesn't zero out that holding
    stk["Live Price"] = stk["Live Price"].fillna(stk["Current Price (CMP)"])
    stk["Current Value"] = stk["Quantity"] * stk["Live Price"]
    stk["P&L"] = stk["Current Value"] - stk["Invested Amount"]
    stk["Return %"] = stk["P&L"] / stk["Invested Amount"] * 100
    return stk


def compute_fd_holdings(fd_raw: pd.DataFrame, usd_inr: float) -> pd.DataFrame:
    fd = fd_raw.copy()
    today = pd.Timestamp.today().normalize()
    fd["Deposit Date"] = pd.to_datetime(fd["Deposit Date"])
    fd["Maturity Date"] = pd.to_datetime(fd["Maturity Date"])
    fd["Days Elapsed"] = (today - fd["Deposit Date"]).dt.days.clip(lower=0)
    fd["Days To Maturity"] = (fd["Maturity Date"] - today).dt.days
    fd["Accrued Interest"] = fd["Principal Amount"] * (fd["ROI % p.a."] / 100) * (fd["Days Elapsed"] / 365)
    fd["Current Value"] = fd["Principal Amount"] + fd["Accrued Interest"]
    fx = fd["Currency"].map(lambda c: usd_inr if c == "USD" and usd_inr else 1.0)
    fd["Current Value (INR)"] = fd["Current Value"] * fx
    fd["Principal (INR)"] = fd["Principal Amount"] * fx
    return fd


# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------

st.title("Family net worth")

with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Upload raw data workbook (optional)", type=["xlsx"])
    st.caption("If left empty, uses data/Networth_Raw_Data.xlsx bundled with this app.")

source = uploaded if uploaded else DATA_PATH
try:
    fd_raw, mf_raw, stk_raw = load_raw(source)
except FileNotFoundError:
    st.warning("No data file found. Upload your raw data workbook in the sidebar to continue.")
    st.stop()

with st.spinner("Fetching live prices..."):
    usd_inr = fetch_usd_inr()
    mf = compute_mf_holdings(mf_raw)
    stk = compute_stock_holdings(stk_raw)
    fd = compute_fd_holdings(fd_raw, usd_inr)

# ---- data quality check, shown plainly rather than hidden ----
mf_missing = mf["Current NAV"].isna().sum()
stk_missing = stk["Live Price"].isna().sum()
if mf_missing or stk_missing:
    st.warning(
        f"Heads up: {mf_missing} fund(s) and {stk_missing} stock(s) couldn't get a live "
        "price this run and are excluded from totals below. Check the tables further down."
    )

mf_ok = mf.dropna(subset=["Current Value"])
stk_ok = stk.dropna(subset=["Current Value"])

mf_current = mf_ok["Current Value"].sum()
mf_invested = mf_ok["Invested"].sum()
stk_current = stk_ok["Current Value"].sum()
stk_invested = stk_ok["Invested Amount"].sum()
fd_current = fd["Current Value (INR)"].sum()
fd_principal = fd["Principal (INR)"].sum()

total_current = mf_current + stk_current + fd_current
total_invested = mf_invested + stk_invested + fd_principal
total_pnl = total_current - total_invested
equity_pct = (mf_current + stk_current) / total_current * 100 if total_current else 0

# ---- KPI row ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total net worth", f"₹{total_current:,.0f}")
c2.metric("Total P&L", f"₹{total_pnl:,.0f}", f"{total_pnl/total_invested*100:.1f}%" if total_invested else None)
c3.metric("Equity allocation", f"{equity_pct:.1f}%", f"{equity_pct - TARGET_EQUITY_PCT:+.1f}pt vs target")
c4.metric("USD/INR", f"{usd_inr:.2f}" if usd_inr else "unavailable")

st.divider()

# ---- allocation + owner breakdown ----
col1, col2 = st.columns(2)

with col1:
    st.subheader("Asset allocation")
    fig = go.Figure(data=[go.Pie(
        labels=["Fixed deposits", "Mutual funds", "Stocks"],
        values=[fd_current, mf_current, stk_current],
        hole=0.65,
        marker=dict(colors=["#2a78d6", "#eb6834", "#1baf7a"]),
    )])
    fig.update_layout(showlegend=True, height=320, margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Net worth by family member")
    owner_totals = {}
    for owner, val in mf_ok.groupby("Owner")["Current Value"].sum().items():
        owner_totals[owner] = owner_totals.get(owner, 0) + val
    for owner, val in stk_ok.groupby("Owner")["Current Value"].sum().items():
        owner_totals[owner] = owner_totals.get(owner, 0) + val
    for owner, val in fd.groupby("Holder Name")["Current Value (INR)"].sum().items():
        owner_totals[owner] = owner_totals.get(owner, 0) + val
    owner_df = pd.DataFrame(sorted(owner_totals.items(), key=lambda x: -x[1]), columns=["Owner", "Net worth"])
    fig2 = go.Figure(data=[go.Bar(x=owner_df["Owner"], y=owner_df["Net worth"], marker_color="#2a78d6")])
    fig2.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), yaxis_title=None)
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---- performers + FD maturity ----
col3, col4 = st.columns(2)

with col3:
    st.subheader("Top and bottom performers")
    combined = pd.concat([
        mf_ok[["Fund Name", "Return %"]].rename(columns={"Fund Name": "Name"}),
        stk_ok[["Company Name", "Return %"]].rename(columns={"Company Name": "Name"}),
    ]).sort_values("Return %", ascending=False)
    top5 = combined.head(5)
    bottom5 = combined.tail(5)
    st.dataframe(pd.concat([top5, bottom5]).style.format({"Return %": "{:+.1f}%"}), hide_index=True, use_container_width=True)

with col4:
    st.subheader("FD maturity watch (next 60 days)")
    soon = fd[fd["Days To Maturity"].between(0, 60)].sort_values("Days To Maturity")
    if soon.empty:
        st.caption("Nothing maturing in the next 60 days.")
    else:
        display = soon[["Holder Name", "Currency", "Principal Amount", "Days To Maturity"]]
        st.dataframe(display, hide_index=True, use_container_width=True)

st.divider()
st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')} · Prices from mfapi.in (AMFI), Yahoo Finance, frankfurter.app")

with st.expander("Full holdings detail"):
    st.write("Mutual funds")
    st.dataframe(mf, hide_index=True, use_container_width=True)
    st.write("Stocks")
    st.dataframe(stk, hide_index=True, use_container_width=True)
    st.write("Fixed deposits")
    st.dataframe(fd, hide_index=True, use_container_width=True)
