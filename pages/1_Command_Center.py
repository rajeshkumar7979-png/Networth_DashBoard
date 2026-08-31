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
import time

st.set_page_config(page_title="Family Net Worth", page_icon="💰", layout="wide", initial_sidebar_state="expanded")

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)
TODAY_NAIVE = pd.Timestamp(now_ist.date())
HISTORY_PATH = "data/history.csv"
AMFI_CACHE_PATH = "data/amfi_nav_cache.json"

# -------------------------------------------------
# THEME
# Collapse Streamlit header so title isn't eaten on mobile Chrome/iOS.
# Extra top padding + safe-area for iPhone. Prefer toolbarMode="minimal"
# in .streamlit/config.toml as well.
# -------------------------------------------------
st.markdown("""
<style>
    .stApp { background: #0a0e17; color: #e5e9f0; }
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0 !important;
        min-height: 0 !important;
        border: none !important;
        padding: 0 !important;
    }
    div[data-testid="stDecoration"] { display: none !important; }
    div[data-testid="stToolbar"] { display: none !important; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    section[data-testid="stSidebar"] { background-color: #0f1420 !important; border-right: 1px solid #1c2333; }
    .main-title {
        font-size: 1.7rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.03em;
        margin: 0 0 0.05rem 0; padding-top: 0.35rem; position: relative; z-index: 2;
    }
    .sub-title { color: #6b7688; font-size: 0.82rem; margin-bottom: 0.8rem; font-weight: 400; }
    .section-header {
        font-size: 0.75rem; font-weight: 700; color: #8b95a8; margin: 1.2rem 0 0.55rem 0;
        text-transform: uppercase; letter-spacing: 0.08em; display: flex; align-items: center; gap: 8px;
    }
    .section-header::after { content: ""; flex: 1; height: 1px; background: #1c2333; }
    div[data-testid="stMetric"] {
        background: linear-gradient(155deg, #12182a 0%, #0e1420 100%);
        border: 1px solid #1c2333; border-radius: 12px; padding: 12px 15px 10px 15px;
    }
    div[data-testid="stMetric"]:hover { border-color: #2a3552; }
    div[data-testid="stMetricValue"] { font-size: 1.3rem !important; font-weight: 700 !important; color: #f8fafc !important; }
    div[data-testid="stMetricLabel"] { color: #6b7688 !important; font-size: 0.67rem !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.05em; }
    div[data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
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
    .block-container {
        padding-top: 1.4rem !important;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    @supports (padding: env(safe-area-inset-top)) {
        .block-container { padding-top: calc(1.4rem + env(safe-area-inset-top)) !important; }
    }
    @media (max-width: 768px) {
        .block-container { padding-top: 1.8rem !important; padding-left: 0.9rem !important; padding-right: 0.9rem !important; }
        .main-title { font-size: 1.45rem; padding-top: 0.5rem; }
        .sub-title { font-size: 0.75rem; }
        div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
    }
    .caveat { font-size: 0.72rem; color: #5b6478; font-style: italic; }
    .recon-pass { color: #22c55e; font-weight: 600; }
    .recon-fail { color: #ef4444; font-weight: 600; }
    /* compact attention grid */
    .flag-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 4px; }
    @media (max-width: 900px) { .flag-grid { grid-template-columns: 1fr; } }
    .flag-card { border-radius: 8px; padding: 7px 10px; margin-bottom: 0; display: flex; gap: 8px; align-items: flex-start; border: 1px solid; }
    .flag-title { font-weight: 600; font-size: 0.78rem; color: #f1f5f9; margin: 0; line-height: 1.25; }
    .flag-body  { font-size: 0.70rem; color: #9aa4b8; margin: 1px 0 0 0; line-height: 1.3; }
    /* market pulse ticker — TradingView-style dark */
    .ticker-wrap { width:100%; overflow:hidden; background:#0b0f18; border:1px solid #1c2333;
                    border-radius:10px; padding:10px 0; white-space:nowrap; margin: 8px 0 4px 0; }
    .ticker-move { display:inline-block; animation: ticker-scroll 50s linear infinite; }
    .ticker-wrap:hover .ticker-move { animation-play-state: paused; }
    @keyframes ticker-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
    .ticker-item { display:inline-flex; align-items:baseline; gap:6px; padding:0 26px;
                   font-size:0.82rem; font-weight:600; color:#e5e9f0; }
    .ticker-name { color:#8b95a8; font-weight:600; letter-spacing:0.02em; }
    .ticker-val { color:#f8fafc; font-variant-numeric: tabular-nums; }
    .ticker-chg { font-weight:700; font-variant-numeric: tabular-nums; }
    .ticker-up .ticker-chg { color:#22c55e; }
    .ticker-down .ticker-chg { color:#ef4444; }
    .ticker-arrow { font-size:0.95rem; font-weight:800; }
    .ticker-up .ticker-arrow { color:#22c55e; }
    .ticker-down .ticker-arrow { color:#ef4444; }
    .ticker-na { color:#5b6478; }
    .crit-banner { background:#3b1219; border:1px solid #7f1d1d; color:#fecaca;
                   border-radius:10px; padding:10px 14px; margin: 8px 0 4px 0; font-size:0.82rem; }
    /* Phase A — command center */
    .pulse-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:8px 0 4px 0; }
    @media (max-width:1100px){ .pulse-grid{ grid-template-columns:repeat(2,minmax(0,1fr));} }
    .pulse-card { background:linear-gradient(155deg,#12182a 0%,#0e1420 100%); border:1px solid #1c2333;
                  border-radius:10px; padding:12px 14px; min-height:78px; overflow:hidden; }
    .pulse-card:hover { border-color:#2a3552; }
    .pulse-label { font-size:0.65rem; font-weight:700; color:#6b7688; text-transform:uppercase; letter-spacing:0.06em; }
    .pulse-val { font-size:1.05rem; font-weight:700; color:#f8fafc; margin-top:2px; font-variant-numeric:tabular-nums; }
    .pulse-chg-up { color:#22c55e; font-size:0.78rem; font-weight:700; }
    .pulse-chg-dn { color:#ef4444; font-size:0.78rem; font-weight:700; }
    .pulse-chg-na { color:#5b6478; font-size:0.78rem; }
    .attn-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:6px 0 8px 0; }
    @media (max-width:1100px){ .attn-grid{ grid-template-columns:repeat(2,1fr);} }
    .attn-tile { border-radius:10px; padding:10px 12px; border:1px solid; min-height:88px; }
    .attn-tag { display:inline-block; font-size:0.60rem; font-weight:800; letter-spacing:0.06em;
                padding:2px 7px; border-radius:4px; margin-bottom:6px; }
    .tag-urgent { background:#7f1d1d; color:#fecaca; }
    .tag-review { background:#78350f; color:#fde68a; }
    .tag-upcoming { background:#1e3a5f; color:#93c5fd; }
    .attn-title { font-size:0.82rem; font-weight:700; color:#f1f5f9; margin:0 0 3px 0; line-height:1.25; }
    .attn-body { font-size:0.70rem; color:#9aa4b8; margin:0; line-height:1.3; }
    .why-box { background:#0f1420; border:1px solid #1c2333; border-radius:10px; padding:10px 14px; margin-top:8px; }
    .why-box li { color:#9aa4b8; font-size:0.78rem; margin:3px 0; }
    .status-row { display:flex; flex-wrap:wrap; gap:10px; margin:6px 0 4px 0; }
    .status-pill { font-size:0.72rem; color:#9aa4b8; background:#0f1420; border:1px solid #1c2333;
                   border-radius:999px; padding:4px 10px; }
    .status-dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; }
    .dot-live { background:#22c55e; }
    .dot-cache { background:#eab308; }
    .dot-off { background:#ef4444; }
    .alloc-legend { list-style:none; margin:8px 0 0 0; padding:0; }
    .alloc-legend li { display:flex; justify-content:space-between; gap:12px; font-size:0.78rem;
                       color:#9aa4b8; padding:4px 0; border-bottom:1px solid #141a28; }
    .alloc-legend .nm { color:#e5e9f0; font-weight:600; }
    .alloc-legend .amt { font-variant-numeric:tabular-nums; color:#c2c9d6; }
    .snap-note { font-size:0.72rem; color:#6b7688; margin-top:4px; }
</style>
""", unsafe_allow_html=True)

def to_naive_ts(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts

# -------------------------------------------------
# DATA SOURCES
# -------------------------------------------------
def _parse_amfi_text(text: str):
    # AMFI format (2024+): SchemeCode;ISIN_G;ISIN_D;Name;Plan;Option;NAV;Date  (8 cols)
    # Older format:         SchemeCode;ISIN_G;ISIN_D;Name;NAV;Date                 (6 cols)
    # Prefer index 6 (new), fall back to index 4 (old).
    nav_dict, code_dict, name_dict = {}, {}, {}
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].strip().isdigit():
            continue
        code = parts[0].strip()
        isin_g, isin_d = parts[1].strip(), parts[2].strip()
        name = parts[3].strip()
        nav = None
        for idx in (6, 4):
            if len(parts) > idx:
                try:
                    nav = float(parts[idx].strip())
                    break
                except Exception:
                    continue
        if nav is None:
            continue
        for isin in (isin_g, isin_d):
            if isin and isin != "-" and len(isin) > 8:
                nav_dict[isin] = nav
                code_dict[isin] = code
                name_dict[isin] = name
    return nav_dict, code_dict, name_dict

def _save_amfi_cache(nav_dict, code_dict, name_dict):
    try:
        os.makedirs("data", exist_ok=True)
        import json
        payload = {
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "nav": nav_dict,
            "code": code_dict,
            "name": name_dict,
        }
        with open(AMFI_CACHE_PATH, "w") as f:
            json.dump(payload, f)
    except Exception:
        pass

def _load_amfi_cache():
    try:
        import json
        if not os.path.exists(AMFI_CACHE_PATH):
            return None
        with open(AMFI_CACHE_PATH) as f:
            payload = json.load(f)
        nav = payload.get("nav") or {}
        if not nav:
            return None
        return nav, payload.get("code") or {}, payload.get("name") or {}, payload.get("saved_at", "unknown")
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_amfi_data():
    # NAV updates once a day. Live fetch + disk fallback so a blocked cloud IP
    # still serves yesterday's file instead of zeroing every fund.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/plain,*/*",
    }
    urls = [
        "https://www.amfiindia.com/spages/NAVAll.txt",
        "https://portal.amfiindia.com/spages/NAVAll.txt",
    ]
    for attempt in range(2):
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=20)
                r.raise_for_status()
                if len(r.text) < 1000:
                    continue
                nav_dict, code_dict, name_dict = _parse_amfi_text(r.text)
                if nav_dict:
                    _save_amfi_cache(nav_dict, code_dict, name_dict)
                    return nav_dict, code_dict, name_dict, None  # None = live
            except Exception:
                continue
        if attempt == 0:
            time.sleep(1.5)
    cached = _load_amfi_cache()
    if cached:
        nav_dict, code_dict, name_dict, saved_at = cached
        return nav_dict, code_dict, name_dict, saved_at  # disk fallback
    return {}, {}, {}, None

@st.cache_data(ttl=21600, show_spinner=False)
def get_mf_nav_history(scheme_code: str):
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
    try:
        hist = yf.Ticker("^NSEI").history(period="5y")
        if hist.empty:
            return None
        df = hist[["Close"]].rename(columns={"Close": "nav"}).reset_index().rename(columns={"Date": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df
    except Exception:
        return None

TROY_OZ_G = 31.1034768  # grams per troy ounce

@st.cache_data(ttl=900, show_spinner=False)
def get_market_pulse_yf(ticker: str):
    """Last close + day change. Ignores absurd gaps (halved contract, empty sessions)."""
    try:
        hist = yf.Ticker(ticker).history(period="15d")
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 1:
            return None
        latest = float(closes.iloc[-1])
        change_pct = None
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            if prev > 0:
                raw = (latest / prev - 1) * 100
                if abs(raw) <= 20:
                    change_pct = raw
                elif len(closes) >= 3:
                    prev2 = float(closes.iloc[-3])
                    if prev2 > 0:
                        change_pct = (latest / prev2 - 1) * 100
                        if abs(change_pct) > 20:
                            change_pct = None
        return {"value": latest, "change_pct": change_pct}
    except Exception:
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def get_ath_pct(ticker: str):
    """% below all-time high (daily close). Free Yahoo history."""
    try:
        hist = yf.Ticker(ticker).history(period="max")
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        ath = float(closes.max())
        latest = float(closes.iloc[-1])
        if ath <= 0:
            return None
        return (latest / ath - 1) * 100
    except Exception:
        return None

@st.cache_data(ttl=900, show_spinner=False)
def get_india_gold_10g():
    """INR per 10g pure gold from goldprice.dev XAU-INR spot (free, no key)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        r = requests.get(
            "https://api.goldprice.dev/v1/prices?symbol=XAU-INR-SPOT",
            headers=headers, timeout=12,
        )
        r.raise_for_status()
        price_oz = float(r.json()["symbols"][0]["price"])
        per_10g = price_oz / TROY_OZ_G * 10.0
        # day change: compare vs Yahoo GC=F move as proxy when prior INR not stored
        chg = None
        y = get_market_pulse_yf("GC=F")
        if y:
            chg = y["change_pct"]
        return {"value": per_10g, "change_pct": chg}
    except Exception:
        # fallback: COMEX oz * USDINR → INR/10g
        try:
            g = get_market_pulse_yf("GC=F")
            fx = get_market_pulse_yf("INR=X")
            if g and fx:
                per_10g = g["value"] / TROY_OZ_G * 10.0 * fx["value"]
                return {"value": per_10g, "change_pct": g["change_pct"]}
        except Exception:
            pass
        return None

@st.cache_data(ttl=900, show_spinner=False)
def get_india_silver_kg():
    """INR per kg silver via COMEX SI=F * USD/INR."""
    try:
        s = get_market_pulse_yf("SI=F")
        fx = get_market_pulse_yf("INR=X")
        if not s or not fx:
            return None
        per_kg = s["value"] / TROY_OZ_G * 1000.0 * fx["value"]
        return {"value": per_kg, "change_pct": s["change_pct"]}
    except Exception:
        return None

def build_market_pulse_rows():
    """India indices, INR metals, global, FX — with ATH% where Yahoo max history is free."""
    rows = []
    # (label, fetcher, fmt, yf_ticker_for_ath or None)
    specs = [
        ("NIFTY 50", lambda: get_market_pulse_yf("^NSEI"), "{:,.2f}", "^NSEI"),
        ("SENSEX", lambda: get_market_pulse_yf("^BSESN"), "{:,.2f}", "^BSESN"),
        ("GOLD ₹/10g", lambda: get_india_gold_10g(), "{:,.0f}", "GC=F"),
        ("SILVER ₹/kg", lambda: get_india_silver_kg(), "{:,.0f}", "SI=F"),
        ("BRENT OIL", lambda: get_market_pulse_yf("BZ=F"), "{:,.2f}", "BZ=F"),
        ("S&P 500", lambda: get_market_pulse_yf("^GSPC"), "{:,.2f}", "^GSPC"),
        ("NASDAQ", lambda: get_market_pulse_yf("^IXIC"), "{:,.2f}", "^IXIC"),
        ("USD/INR", lambda: get_market_pulse_yf("INR=X"), "{:,.2f}", None),
    ]
    for label, fetcher, fmt, ath_ticker in specs:
        d = fetcher()
        ath = get_ath_pct(ath_ticker) if ath_ticker else None
        if d and d.get("value") is not None:
            rows.append({"Market": label, "Value": d["value"], "Chg %": d.get("change_pct"), "ATH %": ath, "fmt": fmt})
        else:
            rows.append({"Market": label, "Value": None, "Chg %": None, "ATH %": ath, "fmt": fmt})
    return rows


def style_money_df(df, pnl_cols=("P&L", "Return %", "FX Gain/Loss (INR)")):
    """Color positive/negative P&L columns for holdings tables."""
    if df is None or df.empty:
        return df
    cols = [c for c in pnl_cols if c in df.columns]
    if not cols:
        return df
    def _clr(v):
        try:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return ""
            return "color: #22c55e" if float(v) >= 0 else "color: #ef4444"
        except Exception:
            return ""
    try:
        return df.style.map(_clr, subset=cols)
    except Exception:
        return df

def trailing_return(hist_df, years):
    if hist_df is None or hist_df.empty:
        return None
    latest_date, latest_nav = hist_df["date"].iloc[-1], hist_df["nav"].iloc[-1]
    target_date = latest_date - pd.Timedelta(days=int(years * 365.25))
    past = hist_df[hist_df["date"] <= target_date]
    if past.empty or latest_nav <= 0:
        return None
    past_nav = past.iloc[-1]["nav"]
    return None if past_nav <= 0 else ((latest_nav / past_nav) ** (1 / years) - 1) * 100

@st.cache_data(ttl=300)
def get_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=8)
        return float(r.json()["rates"]["INR"])
    except Exception:
        return None  # FIXED: no more silent 95.5 fallback — see integrity check below

# NEW — Phase 2 (FCNR audit): historical FX rate as of a specific deposit
# date, so a USD FD's INR cost basis reflects the rate on the day it was
# actually funded, not today's rate. Without this, "Principal (INR)" was
# silently computed with today's FX for BOTH the cost basis and the current
# value, which mathematically erases any FX gain/loss from the P&L — a real
# NRI's rupee depreciation gain over a multi-year FCNR deposit was invisible.
@st.cache_data(ttl=86400, show_spinner=False)
def get_historical_usd_inr(date_str: str):
    try:
        r = requests.get(f"https://api.frankfurter.app/{date_str}?from=USD&to=INR", timeout=8)
        r.raise_for_status()
        rates = r.json().get("rates", {})
        return rates.get("INR")
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def get_groww_ltp(nse_symbol: str):
    """Live LTP from Groww free NSE CASH endpoint (equities + SGBs)."""
    if not nse_symbol:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        r = requests.get(
            f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/exchange/NSE/segment/CASH/{nse_symbol}/latest",
            headers=headers, timeout=10,
        )
        r.raise_for_status()
        ltp = r.json().get("ltp")
        if ltp is not None and float(ltp) > 0:
            return float(ltp)
    except Exception:
        pass
    return None

@st.cache_data(ttl=300)
def get_stock_price(symbol: str):
    if not symbol:
        return None
    # Prefer Groww live LTP; fall back to Yahoo last close
    price = get_groww_ltp(symbol)
    if price is not None:
        return price
    try:
        t = yf.Ticker(f"{symbol}.NS")
        hist = t.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def get_sgb_price(raw_ticker: str):
    # Strip data-entry "-GB" suffix; Yahoo lacks most SGB series — Groww has live NSE LTP
    nse_symbol = re.sub(r"-GB$", "", raw_ticker.strip(), flags=re.IGNORECASE)
    price = get_groww_ltp(nse_symbol)
    if price is not None:
        return price
    try:
        t = yf.Ticker(f"{nse_symbol}.NS")
        hist = t.history(period="5d")
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

def format_inr_indian(num, decimals=0):
    """Indian grouping: 2,68,12,952.00 (lakhs/crores), not Western 26,812,952."""
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return "₹0" if decimals == 0 else "₹0.00"
    try:
        n = float(num)
    except Exception:
        return "₹0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if decimals <= 0:
        int_part = str(int(round(n)))
        frac = ""
    else:
        s = f"{n:.{decimals}f}"
        int_part, frac = s.split(".")
        frac = "." + frac
    # Indian: last 3 digits, then groups of 2
    if len(int_part) <= 3:
        grouped = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(reversed(groups)) + "," + last3
    return f"{sign}₹{grouped}{frac}"

def format_inr(num):
    return format_inr_indian(num, decimals=0)

def format_inr_compact(num):
    """Use Cr / Lakh for large headline metrics."""
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return "₹0"
    try:
        n = float(num)
    except Exception:
        return "₹0"
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1e7:
        return f"{sign}₹{a/1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a/1e5:.2f} L"
    return format_inr_indian(n, decimals=0)

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

CATEGORY_RULES = [
    ("Liquid", r"liquid"), ("Money Market", r"money\s*market"), ("Overnight", r"overnight"),
    ("Small Cap", r"small\s*cap"), ("Mid Cap", r"mid\s*cap"), ("Large Cap", r"large\s*cap|bluechip"),
    ("Flexi Cap", r"flexi\s*cap|multi\s*cap"), ("Index", r"index|next\s*50|nifty\s*50\b"),
    ("Hybrid", r"hybrid|balanced"), ("Contra/Value", r"contra|value\s*discovery"),
    ("Sectoral/Thematic", r"infra|defence|bharat\s*22|fof|reform"),
]
DEBT_LIKE = {"Liquid", "Money Market", "Overnight"}

# Gold instruments: SGB (NSE-listed bonds), gold ETFs (GOLDBEES etc.), and gold FoFs/ETFs in the MF sheet.
# These must appear ONLY under Gold — never under Stocks or Mutual Funds.
SGB_TICKER_PATTERN = re.compile(r"^SGB.*-GB$", re.IGNORECASE)
GOLD_ETF_TICKERS = {"GOLDBEES", "GOLDSHARE", "GOLDCASE", "AXISGOLD", "QGOLDHALF", "BSLGOLDETF", "IVZINGOLD"}
GOLD_FUND_NAME_RE = re.compile(
    r"gold\s*(etf|fof|fund\s*of\s*fund|fund\s*of\s*funds)|\bgold\b.*\b(etf|fof)\b",
    re.IGNORECASE,
)

def is_gold_symbol(symbol: str) -> bool:
    s = (symbol or "").strip().upper()
    if not s:
        return False
    if SGB_TICKER_PATTERN.match(s):
        return True
    if s in GOLD_ETF_TICKERS or s.endswith("GOLD") or "GOLD" in s and s.endswith("ETF"):
        return True
    return False

def is_gold_fund(fund_name: str) -> bool:
    return bool(GOLD_FUND_NAME_RE.search(fund_name or ""))

def infer_category(fund_name: str) -> str:
    name = (fund_name or "").lower()
    if is_gold_fund(fund_name):
        return "Gold"
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
                              help="Free-tier Streamlit storage isn't guaranteed to survive a redeploy — download history periodically.")
    auto_refresh = st.toggle(
        "Auto-refresh every 5 min",
        value=True,
        help="Reloads the whole page every 5 minutes so prices/NAVs stay fresh. Turn off on mobile if it interrupts reading.",
    )
    if st.button("Reset history file", use_container_width=True,
                 help="Deletes corrupted or unwanted history.csv rows."):
        try:
            if os.path.exists(HISTORY_PATH):
                os.remove(HISTORY_PATH)
            st.success("History cleared.")
        except Exception as e:
            st.error(f"Could not clear history: {e}")

    st.markdown("##### Restore history")
    hist_upload = st.file_uploader(
        "Upload previous history CSV to merge",
        type=["csv"],
        help="After a Streamlit Cloud restart, upload a previously downloaded networth_history.csv to restore older days.",
        key="hist_csv_upload",
    )
    if hist_upload is not None:
        try:
            os.makedirs("data", exist_ok=True)
            incoming = pd.read_csv(hist_upload)
            if "date" not in incoming.columns or "net_worth" not in incoming.columns:
                st.error("CSV must have at least date and net_worth columns.")
            else:
                if os.path.exists(HISTORY_PATH):
                    existing = pd.read_csv(HISTORY_PATH)
                    merged = pd.concat([existing, incoming], ignore_index=True)
                else:
                    merged = incoming
                merged["date"] = merged["date"].astype(str)
                merged = merged[merged["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
                for col in ["net_worth", "equity_pct", "fd_pct", "pnl", "health_score"]:
                    if col in merged.columns:
                        merged[col] = pd.to_numeric(merged[col], errors="coerce")
                merged = merged.dropna(subset=["net_worth"])
                # Keep latest row per date
                merged = merged.sort_values("date").drop_duplicates(subset=["date"], keep="last")
                merged.to_csv(HISTORY_PATH, index=False)
                st.success(f"Merged history — {len(merged)} day(s) on disk.")
        except Exception as e:
            st.error(f"Could not merge history: {e}")

    st.markdown("---")
    st.caption("AMFI · Groww · Yahoo · goldprice.dev · Frankfurter · Google News")
    st.caption(f"IST {now_ist.strftime('%d %b %Y, %H:%M')}")

# Auto-refresh: full page reload (no extra package). Only when toggle is on.
if auto_refresh:
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        // Reload parent Streamlit page after 5 minutes
        setTimeout(function () {
            window.parent.location.reload();
        }, 300000);
        </script>
        """,
        height=0,
    )

# -------------------------------------------------
# LOAD + PROCESS
# -------------------------------------------------
fd_raw, mf_raw, stocks_raw = load_data(uploaded)
usd_inr = get_usd_inr()
amfi_navs, amfi_codes, amfi_names, amfi_cache_date = get_amfi_data()
nifty_hist = get_nifty_history()
nifty_1y, nifty_3y, nifty_5y = trailing_return(nifty_hist, 1), trailing_return(nifty_hist, 3), trailing_return(nifty_hist, 5)

# ---- Data integrity log, built up as we go (Phase 3) ----
integrity_issues = []  # each: (severity, message)
if usd_inr is None:
    integrity_issues.append(("CRITICAL", "USD/INR live rate fetch failed this run — all USD FD conversions below are unavailable until it recovers, not silently defaulted to a guessed rate."))
    usd_inr = None

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
    # Aggregate by Owner+ISIN only so name variants (spaces/dashes) of the same
    # fund collapse into one row (fixes split HDFC Liquid / Gold FoF lines).
    def _pick_name(s):
        return max(s.astype(str), key=len)  # longest name is usually the cleanest
    mf_agg = (
        mf_txns_df.groupby(["Owner", "ISIN"], as_index=False)
        .agg({"Units": "sum", "Invested": "sum", "Purchase Date": "min", "Fund Name": _pick_name})
    )
else:
    mf_agg = pd.DataFrame(columns=["Owner", "ISIN", "Fund Name", "Units", "Invested", "Purchase Date"])

mf_rows, gold_rows_from_mf, mf_failed = [], [], 0
for _, row in mf_agg.iterrows():
    try:
        isin, units, invested, pdate = row["ISIN"], row["Units"], row["Invested"], row["Purchase Date"]
        fund_name = str(row["Fund Name"] or "")
        nav = amfi_navs.get(isin)  # None = unknown; do NOT default to 0.0
        if nav is None:
            mf_failed += 1
            integrity_issues.append(("HIGH", f"{fund_name[:40]}: no live NAV found for ISIN {isin} — excluded from totals."))
        if units < 0:
            integrity_issues.append(("HIGH", f"{fund_name[:40]} ({row['Owner']}): negative net units ({units:.2f}) after aggregation — check for a sell exceeding recorded buys."))
        if nav is not None:
            current_value = units * nav
            pnl = current_value - invested
            ret = (pnl / invested * 100) if invested > 0 else 0.0
        else:
            current_value = pnl = ret = None
        category = infer_category(fund_name)

        # Route pure gold FoFs/ETFs out of Mutual Funds into the unified Gold book
        if is_gold_fund(fund_name):
            # Short display symbol for the Gold table (keep it readable)
            sym = "GOLD-FoF"
            if "HDFC" in fund_name.upper():
                sym = "HDFC-GOLD-FoF"
            elif "ICICI" in fund_name.upper():
                sym = "ICICI-GOLD-FoF"
            elif "NIPPON" in fund_name.upper() or "RELIANCE" in fund_name.upper():
                sym = "NIPPON-GOLD-FoF"
            gold_rows_from_mf.append({
                "Owner": row["Owner"], "Symbol": sym, "Quantity": round(units, 3),
                "Invested": invested, "Current Price": nav, "Current Value": current_value,
                "P&L": pnl, "Return %": ret, "Source": "MF",
            })
            continue  # do not also put in mf_rows

        days_held = (TODAY_NAIVE - pdate).days if pdate is not None else None
        fund_return_ann = ((current_value / invested) ** (365.25 / days_held) - 1) * 100 if (current_value is not None and days_held and days_held >= 30 and invested > 0) else None
        code = amfi_codes.get(isin)
        r1y = r3y = r5y = b1y = b3y = b5y = None
        if category not in DEBT_LIKE and code:
            fund_hist = get_mf_nav_history(code)
            r1y, r3y, r5y = trailing_return(fund_hist, 1), trailing_return(fund_hist, 3), trailing_return(fund_hist, 5)
            b1y, b3y, b5y = nifty_1y, nifty_3y, nifty_5y
        mf_rows.append({
            "Owner": row["Owner"], "ISIN": isin, "Fund Name": fund_name[:42], "Category": category,
            "Units": round(units, 3), "Invested": invested, "Current NAV": nav, "Current Value": current_value,
            "P&L": pnl, "Return %": ret, "Ann. Return %": fund_return_ann,
            "1Y %": r1y, "3Y %": r3y, "5Y %": r5y, "vs Nifty50 1Y": b1y, "vs Nifty50 3Y": b3y, "vs Nifty50 5Y": b5y,
            "Purchase Date": pdate,
        })
    except Exception:
        mf_failed += 1
mf = pd.DataFrame(mf_rows)

# Gold book: SGB + gold ETFs (from Stocks sheet) + gold FoFs (from MF sheet above).
# All gold exposure lives in exactly one place.
stock_rows, gold_rows = [], []
for _, row in stocks_raw.iterrows():
    try:
        symbol = str(row.get("Symbol", row.get("Ticker / Symbol", "")) or "").strip().upper()
        qty = safe_float(row.get("Quantity"))
        invested = safe_float(row.get("Invested Amount"))
        if qty <= 0:
            continue
        is_gold = is_gold_symbol(symbol)
        if is_gold and SGB_TICKER_PATTERN.match(symbol):
            price = get_sgb_price(symbol)
        else:
            price = get_stock_price(symbol) if symbol else None
        used_fallback = False
        if price is None:
            price = safe_float(row.get("Current Price", row.get("Current Price (CMP)")))
            used_fallback = True
            if price == 0:
                price = safe_float(row.get("Purchase Price", row.get("Avg Buy Price")))
        if used_fallback:
            integrity_issues.append(("MEDIUM", f"{symbol}: live price unavailable, used stale price from the raw file instead."))
        if price and price > 0:
            current_value = qty * price
            pnl = current_value - invested
            ret = (pnl / invested * 100) if invested > 0 else 0.0
        else:
            current_value = pnl = ret = None
            price = None
            integrity_issues.append(("HIGH", f"{symbol}: no valid price from any source — excluded from totals."))
        # Only flag extreme P&L when it looks like a possible data error (very large
        # multiple). Long-held winners at low cost basis are normal and noisy here.
        if invested > 0 and pnl is not None and abs(pnl) > invested * 10:
            integrity_issues.append(("MEDIUM", f"{symbol}: P&L is {pnl/invested*100:.0f}% of invested amount — unusually large; confirm quantity/price if this was a recent buy."))
        row_dict = {"Owner": str(row.get("Owner", "") or ""), "Symbol": symbol, "Quantity": qty,
                    "Invested": invested, "Current Price": price, "Current Value": current_value,
                    "P&L": pnl, "Return %": ret, "Source": "Stocks"}
        if is_gold:
            gold_rows.append(row_dict)
        else:
            stock_rows.append(row_dict)
    except Exception:
        continue

# Merge gold from Stocks sheet + gold FoFs routed out of MF, then collapse
# any remaining same-owner/same-symbol splits (e.g. FoF name variants).
gold_rows.extend(gold_rows_from_mf)
stocks = pd.DataFrame(stock_rows)
gold = pd.DataFrame(gold_rows)
if not gold.empty and {"Owner", "Symbol", "Quantity", "Invested", "Current Value"}.issubset(gold.columns):
    g_sum = gold.groupby(["Owner", "Symbol"], as_index=False).agg({
        "Quantity": "sum",
        "Invested": "sum",
        "Current Value": "sum",
        "Source": "first",
    })
    g_sum["Current Price"] = g_sum.apply(
        lambda r: (r["Current Value"] / r["Quantity"]) if r["Quantity"] and r["Quantity"] > 0 and pd.notna(r["Current Value"]) else None,
        axis=1,
    )
    g_sum["P&L"] = g_sum["Current Value"] - g_sum["Invested"]
    g_sum["Return %"] = g_sum.apply(
        lambda r: (r["P&L"] / r["Invested"] * 100) if r["Invested"] and r["Invested"] > 0 and pd.notna(r["P&L"]) else None,
        axis=1,
    )
    gold = g_sum

# ---- FD: full native/reporting currency model (Phase 2 & 6 fix) ----
fd_rows = []
seen_accounts = set()
seen_fingerprints = set()  # catches exact clones when Account Number is blank/missing
for _, row in fd_raw.iterrows():
    try:
        holder = str(row.get("Holder Name", "") or "").strip()
        account = str(row.get("Account Number", "") or "").strip()
        if account.lower() in ("nan", "none", "nat", "-"):
            account = ""
        principal_native = safe_float(row.get("Principal Amount"))
        if (not holder or holder.lower() in ["nan", "nat", "none"] or principal_native <= 0 or "total" in holder.lower()):
            continue

        currency = str(row.get("Currency", "INR") or "INR").upper().strip()
        if currency not in ["INR", "USD"]:
            integrity_issues.append(("HIGH", f"FD {account or 'no-acct'} ({holder}): unrecognized currency '{currency}' — treated as INR."))
            currency = "INR"

        mat_date = to_naive_ts(row.get("Maturity Date"))
        dep_date = to_naive_ts(row.get("Deposit Date"))
        roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))

        # Dedup key: prefer real account number; otherwise fingerprint of the deposit itself
        if account:
            dedup_key = f"acct:{account}"
        else:
            mat_s = mat_date.strftime("%Y-%m-%d") if mat_date is not None else ""
            dep_s = dep_date.strftime("%Y-%m-%d") if dep_date is not None else ""
            dedup_key = f"fp:{holder}|{currency}|{principal_native:.2f}|{roi:.4f}|{mat_s}|{dep_s}"

        if dedup_key in seen_accounts or dedup_key in seen_fingerprints:
            integrity_issues.append((
                "CRITICAL",
                f"Duplicate FD skipped — {holder} {currency} {principal_native:,.2f} "
                f"({'acct ' + account if account else 'no account #, identical principal/dates/ROI'}). "
                f"Fix the Excel so this row is not counted twice."
            ))
            continue  # do NOT double-count
        if account:
            seen_accounts.add(dedup_key)
        else:
            seen_fingerprints.add(dedup_key)

        if mat_date is not None and dep_date is not None and mat_date < dep_date:
            integrity_issues.append(("HIGH", f"FD {account or 'no-acct'} ({holder}): maturity date is before deposit date — dates likely swapped in source data."))
        days_to_mat = (mat_date - TODAY_NAIVE).days if mat_date is not None else None
        days_elapsed = (TODAY_NAIVE - dep_date).days if dep_date is not None else 0
        if roi <= 0 or roi > 15:
            integrity_issues.append(("MEDIUM", f"FD {account or 'no-acct'} ({holder}): ROI {roi}% p.a. is outside a normal FD range — verify."))

        accrued_native = principal_native * (roi / 100) * (max(days_elapsed, 0) / 365)
        current_value_native = principal_native + accrued_native

        # Native/reporting split: principal at deposit-date FX; current value at today's FX
        fx_today = usd_inr if currency == "USD" else 1.0
        fx_deposit = 1.0
        if currency == "USD" and dep_date is not None and usd_inr is not None:
            fx_deposit = get_historical_usd_inr(dep_date.strftime("%Y-%m-%d")) or usd_inr
        elif currency == "USD":
            fx_deposit = usd_inr or 1.0

        principal_inr_at_cost = principal_native * fx_deposit if fx_today is not None else None
        current_value_inr = current_value_native * fx_today if fx_today is not None else None
        interest_return_inr = (accrued_native * fx_deposit) if (currency == "USD" and fx_today is not None) else accrued_native
        fx_gain_inr = ((principal_native * fx_today) - (principal_native * fx_deposit)) if (currency == "USD" and fx_today is not None) else 0.0

        # NRI book: USD deposits are treated as FCNR (interest + FX), not resident INR FDs
        product = "FCNR" if currency == "USD" else "INR FD"
        fd_rows.append({
            "Holder Name": holder, "Account Number": account, "Currency": currency,
            "Product": product,
            "Principal (Native)": round(principal_native, 2),
            "Principal (INR, at deposit FX)": round(principal_inr_at_cost, 0) if principal_inr_at_cost is not None else None,
            "ROI %": roi, "Days to Maturity": days_to_mat,
            "Current Value (Native)": round(current_value_native, 2),
            "Current Value (INR)": round(current_value_inr, 0) if current_value_inr is not None else None,
            "Interest Return (INR)": round(interest_return_inr, 0) if interest_return_inr is not None else None,
            "FX Gain/Loss (INR)": round(fx_gain_inr, 0),
            "Maturity Date": mat_date.strftime("%Y-%m-%d") if mat_date is not None else "",
        })
    except Exception:
        continue
fd = pd.DataFrame(fd_rows)
fd_fx_unavailable = fd["Current Value (INR)"].isna().sum() if not fd.empty else 0
if fd_fx_unavailable:
    integrity_issues.append(("CRITICAL", f"{fd_fx_unavailable} USD FD(s) excluded from INR totals — live FX rate unavailable this run."))

# -------------------------------------------------
# AGGREGATES — only rows with a real current value count toward totals
# -------------------------------------------------
mf_valid = mf.dropna(subset=["Current Value"]) if not mf.empty else mf
stocks_valid = stocks.dropna(subset=["Current Value"]) if not stocks.empty else stocks
gold_valid = gold.dropna(subset=["Current Value"]) if not gold.empty else gold
fd_valid = fd.dropna(subset=["Current Value (INR)"]) if not fd.empty else fd

total_mf = mf_valid["Current Value"].sum() if not mf_valid.empty else 0
total_stocks = stocks_valid["Current Value"].sum() if not stocks_valid.empty else 0
total_gold = gold_valid["Current Value"].sum() if not gold_valid.empty else 0
total_fd = fd_valid["Current Value (INR)"].sum() if not fd_valid.empty else 0
total_networth = total_mf + total_stocks + total_gold + total_fd
total_fd_invested = fd_valid["Principal (INR, at deposit FX)"].sum() if not fd_valid.empty else 0
total_invested = ((mf_valid["Invested"].sum() if not mf_valid.empty else 0)
                  + (stocks_valid["Invested"].sum() if not stocks_valid.empty else 0)
                  + (gold_valid["Invested"].sum() if not gold_valid.empty else 0)
                  + total_fd_invested)
total_pnl = total_networth - total_invested

# --- NRI split: equity (ex-liquid MF) vs liquid MF vs INR FD vs FCNR vs gold ---
if not mf_valid.empty and "Category" in mf_valid.columns:
    _liq_mask = mf_valid["Category"].isin(DEBT_LIKE)
    total_liquid_mf = float(mf_valid.loc[_liq_mask, "Current Value"].sum() or 0)
    total_equity_mf = float(mf_valid.loc[~_liq_mask, "Current Value"].sum() or 0)
else:
    total_liquid_mf, total_equity_mf = 0.0, float(total_mf or 0)
total_equity = total_equity_mf + total_stocks
if not fd_valid.empty and "Product" in fd_valid.columns:
    total_fcnr = float(fd_valid.loc[fd_valid["Product"] == "FCNR", "Current Value (INR)"].sum() or 0)
    total_inr_fd = float(fd_valid.loc[fd_valid["Product"] == "INR FD", "Current Value (INR)"].sum() or 0)
elif not fd_valid.empty and "Currency" in fd_valid.columns:
    total_fcnr = float(fd_valid.loc[fd_valid["Currency"] == "USD", "Current Value (INR)"].sum() or 0)
    total_inr_fd = float(fd_valid.loc[fd_valid["Currency"] != "USD", "Current Value (INR)"].sum() or 0)
else:
    total_fcnr, total_inr_fd = 0.0, float(total_fd or 0)

# Near-term maturities (≤90d) count toward usable liquidity for an NRI
if not fd_valid.empty and "Days to Maturity" in fd_valid.columns:
    _near = fd_valid[fd_valid["Days to Maturity"].between(0, 90)]
    total_near_fd = float(_near["Current Value (INR)"].sum() or 0) if not _near.empty else 0.0
else:
    total_near_fd = 0.0
total_true_liquid = total_liquid_mf + total_near_fd

def _pct(part):
    return (part / total_networth * 100) if total_networth else 0.0

equity_pct = _pct(total_equity)          # stocks + non-liquid MF only
liquid_mf_pct = _pct(total_liquid_mf)
inr_fd_pct = _pct(total_inr_fd)
fcnr_pct = _pct(total_fcnr)
gold_pct = _pct(total_gold)
# Backward-compatible: all deposits as share of NW (history still uses this key)
fd_pct = _pct(total_fd)
true_liquid_pct = _pct(total_true_liquid)

top5_mf_pct = (mf_valid.nlargest(5, "Current Value")["Current Value"].sum() / total_mf * 100) if not mf_valid.empty and total_mf > 0 else 0
top5_stock_pct = (stocks_valid.nlargest(5, "Current Value")["Current Value"].sum() / total_stocks * 100) if not stocks_valid.empty and total_stocks > 0 else 0
total_fx_gain = fd_valid["FX Gain/Loss (INR)"].sum() if not fd_valid.empty else 0
total_fcnr_interest = 0.0
if not fd_valid.empty and "Product" in fd_valid.columns and "Interest Return (INR)" in fd_valid.columns:
    total_fcnr_interest = float(fd_valid.loc[fd_valid["Product"] == "FCNR", "Interest Return (INR)"].sum() or 0)

# -------------------------------------------------
# HEALTH SCORE — NRI-aware
# Liquidity scores *true* liquidity (liquid MF + FDs ≤90d), not all FCNR as locked cash.
# Allocation still tracks equity share but narrative treats FCNR as intentional USD book.
# -------------------------------------------------
def score_allocation(equity_pct, target=50):
    # Softer resident-60% target: NRI books often run lower equity by design
    return max(0, 100 - abs(equity_pct - target) * 1.6)
def score_concentration(top5_pct):
    if top5_pct <= 35: return 100
    if top5_pct >= 80: return 0
    return 100 - (top5_pct - 35) / 45 * 100
def score_liquidity_nri(true_liquid_pct):
    # Adequate deployable liquidity for NRI: ~12–35% of NW in liquid MF + near maturities
    if 12 <= true_liquid_pct <= 35: return 100
    if true_liquid_pct < 12: return max(0, 100 - (12 - true_liquid_pct) * 5)
    return max(0, 100 - (true_liquid_pct - 35) * 1.5)
def score_diversification(mf_df):
    if mf_df.empty:
        return 50
    cat = mf_df.groupby("Category")["Current Value"].sum()
    if cat.sum() == 0:
        return 50
    hhi = ((cat / cat.sum()) ** 2).sum()
    return min(100, max(0, (1 - hhi) * 100 / 0.85))
def score_performance(mf_df):
    valid = mf_df.dropna(subset=["1Y %", "vs Nifty50 1Y"])
    return (valid["1Y %"] > valid["vs Nifty50 1Y"]).mean() * 100 if not valid.empty else 60

alloc_score = score_allocation(equity_pct)
conc_score = min(score_concentration(top5_mf_pct), score_concentration(top5_stock_pct) if not stocks_valid.empty else 100)
liq_score = score_liquidity_nri(true_liquid_pct)
div_score = score_diversification(mf_valid)
perf_score = score_performance(mf_valid)
WEIGHTS = {"Allocation": 0.26, "Concentration": 0.20, "Liquidity": 0.20, "Diversification": 0.14, "Performance": 0.20}
factor_scores = {"Allocation": alloc_score, "Concentration": conc_score, "Liquidity": liq_score, "Diversification": div_score, "Performance": perf_score}
health_score = sum(factor_scores[k] * WEIGHTS[k] for k in WEIGHTS)
health_label = "Healthy" if health_score >= 75 else ("Adequate" if health_score >= 55 else "Needs Attention")

# -------------------------------------------------
# RECONCILIATION TESTS (Phase 4) — shown, not hidden, pass or fail
# -------------------------------------------------
recon_tests = []
owner_sum = 0
owner_map = {}
for df_, col, key in [(mf_valid, "Current Value", "Owner"), (stocks_valid, "Current Value", "Owner"),
                       (gold_valid, "Current Value", "Owner"), (fd_valid, "Current Value (INR)", "Holder Name")]:
    if not df_.empty and key in df_.columns:
        for owner, val in df_.groupby(key)[col].sum().items():
            owner_map[owner] = owner_map.get(owner, 0) + val
owner_sum = sum(owner_map.values())
recon_tests.append(("Sum of owner totals = total net worth", abs(owner_sum - total_networth) < 1, f"{format_inr(owner_sum)} vs {format_inr(total_networth)}"))
# Equity (ex-liquid) + liquid MF + INR FD + FCNR + gold should ≈ 100%
alloc_sum = equity_pct + liquid_mf_pct + inr_fd_pct + fcnr_pct + gold_pct
recon_tests.append(("NRI allocation slices sum to 100%", abs(alloc_sum - 100) < 0.6, f"{alloc_sum:.2f}%"))
recon_tests.append(("Portfolio total = MF + Stocks + Gold + FD", abs((total_mf + total_stocks + total_gold + total_fd) - total_networth) < 1, "by construction"))
recon_tests.append((
    "FCNR + INR FD = total deposits",
    abs((total_fcnr + total_inr_fd) - total_fd) < 1,
    f"FCNR {format_inr(total_fcnr)} + INR FD {format_inr(total_inr_fd)}",
))
_gold_leaked_stocks = any(is_gold_symbol(s) for s in stocks["Symbol"]) if not stocks.empty else False
_gold_leaked_mf = any(is_gold_fund(n) for n in mf["Fund Name"]) if not mf.empty else False
recon_tests.append((
    "Gold instruments only in Gold (not Stocks/MF)",
    (not _gold_leaked_stocks) and (not _gold_leaked_mf),
    f"{len(gold)} gold holding(s) · leaked stocks={_gold_leaked_stocks} mf={_gold_leaked_mf}",
))

# -------------------------------------------------
# RED FLAGS
# -------------------------------------------------
flags = []
if equity_pct < 35:
    gap_to_40 = max(0, 0.40 * total_networth - total_equity)
    gap_to_50 = max(0, 0.50 * total_networth - total_equity)
    flags.append((
        "critical" if equity_pct < 20 else "warning",
        "Equity allocation (NRI view)",
        f"Equity (stocks + non-liquid MF) is {equity_pct:.1f}% of NW. "
        f"FCNR {fcnr_pct:.1f}% · INR FD {inr_fd_pct:.1f}% · Liquid MF {liquid_mf_pct:.1f}%. "
        f"~{format_inr(gap_to_40)} more equity → 40%; ~{format_inr(gap_to_50)} → 50%. "
        f"FCNR is intentional USD book (interest + FX), not generic cash.",
    ))
if fcnr_pct >= 15:
    flags.append((
        "info",
        "FCNR / USD deposit book",
        f"FCNR is {fcnr_pct:.1f}% of NW ({format_inr(total_fcnr)}). "
        f"Return = interest (~{format_inr(total_fcnr_interest)}) + FX vs deposit-date USD/INR (~{format_inr(total_fx_gain)}).",
    ))
if 3 <= gold_pct <= 15:
    flags.append(("info", "Gold allocation healthy",
                   f"Gold (SGB + ETFs + FoFs) is {gold_pct:.1f}% of net worth — a reasonable diversifier."))
elif gold_pct > 15:
    flags.append(("info", "Gold allocation is notable", f"Gold (SGB + ETFs + FoFs) is {gold_pct:.1f}% of net worth."))
if top5_mf_pct > 60:
    flags.append(("warning", "Mutual fund concentration", f"Top 5 funds are {top5_mf_pct:.1f}% of your MF portfolio."))
if not stocks_valid.empty and top5_stock_pct > 65:
    flags.append(("warning", "Stock concentration", f"Top 5 stocks are {top5_stock_pct:.1f}% of your equity holdings."))
if not mf_valid.empty:
    persistent = mf_valid.dropna(subset=["1Y %", "3Y %", "vs Nifty50 1Y", "vs Nifty50 3Y"])
    persistent = persistent[(persistent["1Y %"] < persistent["vs Nifty50 1Y"] - 2) & (persistent["3Y %"] < persistent["vs Nifty50 3Y"] - 2)]
    for _, r in persistent.sort_values("1Y %").head(3).iterrows():
        flags.append(("warning", f"{r['Fund Name']}: persistent underperformance",
                       f"Trailing both 1Y ({r['1Y %']:.1f}% vs Nifty50 {r['vs Nifty50 1Y']:.1f}%) and 3Y ({r['3Y %']:.1f}% vs Nifty50 {r['vs Nifty50 3Y']:.1f}%)."))
    losers = mf_valid[mf_valid["Return %"] < -10]
    for _, r in losers.sort_values("Return %").head(3).iterrows():
        pnl_abs = abs(r["P&L"]) if pd.notna(r.get("P&L")) else 0
        flags.append(("critical", f"{r['Fund Name'][:28]} down {abs(r['Return %']):.1f}%",
                       f"Loss {format_inr(pnl_abs)} · currently a loss position."))
if not stocks_valid.empty:
    losers_s = stocks_valid[stocks_valid["Return %"] < -15]
    # Per-owner equity book for context
    owner_eq = stocks_valid.groupby("Owner")["Current Value"].sum().to_dict() if "Owner" in stocks_valid.columns else {}
    for _, r in losers_s.sort_values("Return %").head(3).iterrows():
        pnl_abs = abs(r["P&L"]) if pd.notna(r.get("P&L")) else 0
        own = r.get("Owner", "")
        book = owner_eq.get(own, 0) or 0
        pct_book = (pnl_abs / book * 100) if book > 0 else 0
        flags.append(("critical", f"{r['Symbol']} down {abs(r['Return %']):.1f}%",
                       f"Loss {format_inr(pnl_abs)}"
                       + (f" · {pct_book:.0f}% of {own.split()[-1]}'s stock book" if own and book else "")
                       + "."))
if not fd.empty:
    overdue = fd[fd["Days to Maturity"] < 0]
    for _, r in overdue.iterrows():
        cv = r['Current Value (INR)']
        flags.append(("critical", f"{r['Holder Name']}'s FD matured {abs(int(r['Days to Maturity']))}d ago, uncollected",
                       f"{format_inr(cv) if pd.notna(cv) else r['Current Value (Native)']} — likely earning the bank's default rate instead of {r['ROI %']:.2f}%."))
    soon = fd[fd["Days to Maturity"].between(0, 14)]
    # Rough liquid-MF stock for context on near-maturity FDs
    liq_cv = 0.0
    if not mf_valid.empty and "Category" in mf_valid.columns:
        liq_cv = float(mf_valid[mf_valid["Category"] == "Liquid"]["Current Value"].sum() or 0)
    for _, r in soon.iterrows():
        cv = r['Current Value (INR)']
        body = f"{format_inr(cv) if pd.notna(cv) else r['Current Value (Native)']} — decide reinvest vs deploy elsewhere."
        if liq_cv > 0:
            body += f" Liquid MFs already hold ~{format_inr(liq_cv)}."
        flags.append(("info", f"{r['Holder Name']}'s FD matures in {int(r['Days to Maturity'])}d", body))
critical_integrity = [i for i in integrity_issues if i[0] == "CRITICAL"]
for _, msg in critical_integrity:
    flags.append(("critical", "Data integrity issue", msg))
severity_rank = {"critical": 0, "warning": 1, "info": 2}
flags.sort(key=lambda f: severity_rank[f[0]])

# -------------------------------------------------
# NEWS
# -------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news_for(names, max_items=10):
    """Pull recent Google News RSS for each name; dedupe by title."""
    items, seen = [], set()
    cutoff = datetime.now() - timedelta(days=45)
    for name in names[:12]:
        if not name or not str(name).strip():
            continue
        try:
            q = requests.utils.quote(str(name).strip())
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:
                title = (entry.title or "").strip()
                if not title or title in seen:
                    continue
                pub = datetime(*entry.published_parsed[:6]) if hasattr(entry, "published_parsed") and entry.published_parsed else None
                if pub and pub < cutoff:
                    continue
                seen.add(title)
                items.append({
                    "title": title, "link": entry.link,
                    "source": entry.get("source", {}).get("title", "") if hasattr(entry, "source") else "",
                    "published": entry.get("published", ""), "pub_dt": pub or datetime.min,
                    "query": str(name).strip(),
                })
        except Exception:
            continue
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:max_items]

# -------------------------------------------------
# HISTORY — FIXED: full precision kept in the CSV/download, rounded only
# for on-screen display (Phase 7)
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

def _clean_history(df):
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame(columns=["date", "net_worth", "equity_pct", "fd_pct", "pnl", "health_score"])
    df = df.copy()
    df["date"] = df["date"].astype(str)
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    for col in ["net_worth", "equity_pct", "fd_pct", "pnl", "health_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["net_worth"])
    return df.reset_index(drop=True)

history_df = log_history_snapshot() if log_snapshot else (pd.read_csv(HISTORY_PATH) if os.path.exists(HISTORY_PATH) else pd.DataFrame())
history_df = _clean_history(history_df)
# rewrite cleaned history so bad rows don't keep coming back
if log_snapshot and not history_df.empty:
    try:
        history_df.to_csv(HISTORY_PATH, index=False)
    except Exception:
        pass

# Quick exports (sidebar)
with st.sidebar:
    st.markdown("### Quick actions")
    if history_df is not None and not history_df.empty:
        st.download_button(
            "Download history CSV",
            data=history_df.to_csv(index=False).encode("utf-8"),
            file_name="networth_history.csv",
            mime="text/csv",
            use_container_width=True,
        )
    # Holdings export
    _parts = []
    if not mf_valid.empty:
        _m = mf_valid.copy(); _m["Asset"] = "MF"; _parts.append(_m)
    if not stocks_valid.empty:
        _s = stocks_valid.copy(); _s["Asset"] = "Stock"; _parts.append(_s)
    if not gold_valid.empty:
        _g = gold_valid.copy(); _g["Asset"] = "Gold"; _parts.append(_g)
    if _parts:
        _hold = pd.concat(_parts, ignore_index=True, sort=False)
        st.download_button(
            "Download holdings CSV",
            data=_hold.to_csv(index=False).encode("utf-8"),
            file_name="networth_holdings.csv",
            mime="text/csv",
            use_container_width=True,
        )
    st.markdown("---")
    st.caption("AMFI · Groww · Yahoo · goldprice.dev · Frankfurter")

# ==================================================
# HEADER — command center
# ==================================================
st.markdown('<div class="main-title">Family Net Worth</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">Portfolio Command Center · Last updated {now_ist.strftime("%d %b %Y, %H:%M IST")}</div>', unsafe_allow_html=True)

# Data status pills
amfi_dot = "dot-off" if len(amfi_navs) == 0 else ("dot-cache" if amfi_cache_date else "dot-live")
amfi_lbl = "AMFI offline" if len(amfi_navs) == 0 else ("AMFI cache" if amfi_cache_date else "AMFI live")
stocks_ok = (not stocks.empty and stocks["Current Price"].notna().any()) if not stocks.empty else False
gold_ok = (not gold.empty and gold["Current Price"].notna().any()) if not gold.empty else False
fx_ok = usd_inr is not None
status_html = (
    f'<div class="status-row">'
    f'<span class="status-pill"><span class="status-dot {amfi_dot}"></span>{amfi_lbl} ({len(amfi_navs)})</span>'
    f'<span class="status-pill"><span class="status-dot {"dot-live" if stocks_ok else "dot-off"}"></span>Stocks {"live" if stocks_ok else "n/a"}</span>'
    f'<span class="status-pill"><span class="status-dot {"dot-live" if gold_ok else "dot-off"}"></span>Gold {"live" if gold_ok else "n/a"}</span>'
    f'<span class="status-pill"><span class="status-dot {"dot-live" if fx_ok else "dot-off"}"></span>FX {"live" if fx_ok else "n/a"}</span>'
    f'<span class="status-pill"><span class="status-dot dot-live"></span>Market pulse</span>'
    f'</div>'
)
st.markdown(status_html, unsafe_allow_html=True)

if len(amfi_navs) == 0:
    st.error("AMFI data failed to load this run and no disk cache found — mutual fund values below are excluded.")
elif amfi_cache_date:
    st.warning(f"AMFI live fetch failed — using disk cache from {amfi_cache_date} · {len(amfi_navs)} NAVs")
elif mf_failed > 0:
    st.warning(f"{mf_failed} fund(s) missing a live NAV · {len(amfi_navs)} AMFI NAVs OK")

# Headline metrics — compact Cr form + optional vs prior history day
_prev_nw = _prev_eq = None
if history_df is not None and not history_df.empty and "net_worth" in history_df.columns:
    try:
        _hist_sorted = history_df.sort_values("date")
        if len(_hist_sorted) >= 2:
            _prev_nw = float(_hist_sorted["net_worth"].iloc[-2])
            _prev_eq = float(_hist_sorted["equity_pct"].iloc[-2]) if "equity_pct" in _hist_sorted.columns else None
        elif len(_hist_sorted) == 1 and str(_hist_sorted["date"].iloc[-1]) != now_ist.strftime("%Y-%m-%d"):
            _prev_nw = float(_hist_sorted["net_worth"].iloc[-1])
    except Exception:
        pass
_nw_delta = None
if _prev_nw and _prev_nw > 0:
    _nw_delta = f"{(total_networth - _prev_nw) / _prev_nw * 100:+.2f}% vs prior snapshot"

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Net Worth (INR)", format_inr_compact(total_networth), _nw_delta)
k2.metric("Invested Capital", format_inr_compact(total_invested), "Total amount invested")
k3.metric("Total P&L", format_inr_compact(total_pnl), f"{(total_pnl/total_invested*100):.1f}% overall" if total_invested else None)
k4.metric("Equity (ex-liquid)", f"{equity_pct:.1f}%", "NRI view · stocks + non-liquid MF")
k5.metric("FCNR (USD)", f"{fcnr_pct:.1f}%", f"INR FD {inr_fd_pct:.1f}% · Liquid {liquid_mf_pct:.1f}%")
k6.metric("Health Score", f"{health_score:.0f} / 100", health_label)

# ==================================================
# MARKET PULSE — card grid (Phase A)
# ==================================================
st.markdown('<div class="section-header">Market pulse</div>', unsafe_allow_html=True)
pulse_rows = build_market_pulse_rows()
pulse_cards = []
for row in pulse_rows:
    if row["Value"] is None:
        chg_html = '<div class="pulse-chg-na">—</div>'
        val = "—"
    else:
        val = row["fmt"].format(row["Value"])
        chg = row["Chg %"]
        if chg is None:
            chg_html = '<div class="pulse-chg-na">—</div>'
        elif chg >= 0:
            chg_html = f'<div class="pulse-chg-up">▲ {chg:+.2f}%</div>'
        else:
            chg_html = f'<div class="pulse-chg-dn">▼ {chg:+.2f}%</div>'
    ath = row.get("ATH %")
    if ath is not None:
        ath_html = f'<div class="pulse-chg-na" style="font-size:0.68rem">{ath:.1f}% from ATH</div>'
    else:
        ath_html = ""
    pulse_cards.append(
        f'<div class="pulse-card"><div class="pulse-label">{row["Market"]}</div>'
        f'<div class="pulse-val">{val}</div>{chg_html}{ath_html}</div>'
    )
st.markdown(f'<div class="pulse-grid">{"".join(pulse_cards)}</div>', unsafe_allow_html=True)
st.caption("Free delayed sources · Gold ₹/10g & Silver ₹/kg (INR) · day change vs prior close · ATH from Yahoo daily history")

# ==================================================
# CRITICAL integrity
# ==================================================
crit = [m for sev, m in integrity_issues if sev == "CRITICAL"]
if crit:
    bullets = "".join(f"<div>• {c}</div>" for c in crit[:6])
    st.markdown(f'<div class="crit-banner"><b>Critical data issues</b>{bullets}</div>', unsafe_allow_html=True)

# ==================================================
# WHAT NEEDS MY ATTENTION — tagged tiles
# ==================================================
st.markdown(f'<div class="section-header">What needs my attention · {len(flags)} item(s)</div>', unsafe_allow_html=True)
if not flags:
    st.info("Nothing flagged right now.")
else:
    tiles = []
    for level, title, body in flags[:8]:
        if level == "critical":
            tag, tag_cls, border = "URGENT", "tag-urgent", "#7f1d1d"
        elif level == "warning":
            tag, tag_cls, border = "REVIEW", "tag-review", "#78350f"
        else:
            tag, tag_cls, border = "UPCOMING", "tag-upcoming", "#1e3a5f"
        tiles.append(
            f'<div class="attn-tile" style="border-color:{border};background:#0f1420">'
            f'<span class="attn-tag {tag_cls}">{tag}</span>'
            f'<p class="attn-title">{title}</p>'
            f'<p class="attn-body">{body}</p></div>'
        )
    st.markdown(f'<div class="attn-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)

# ==================================================
# DATA INTEGRITY (Phase 3) — visible, not buried
# ==================================================
if integrity_issues:
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    integrity_issues.sort(key=lambda x: sev_order.get(x[0], 9))
    with st.expander(f"Data integrity check — {len(integrity_issues)} issue(s) found"):
        for sev, msg in integrity_issues:
            st.markdown(f"**{sev}** — {msg}")

# ==================================================
# RECONCILIATION (Phase 4)
# ==================================================
st.markdown('<div class="section-header">Reconciliation</div>', unsafe_allow_html=True)
for name, passed, detail in recon_tests:
    cls = "recon-pass" if passed else "recon-fail"
    mark = "✓ PASS" if passed else "✗ FAIL"
    st.markdown(f'<span class="{cls}">{mark}</span> — {name} ({detail})', unsafe_allow_html=True)

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
    st.plotly_chart(fig_h, use_container_width=True, key="chart_health")

    _why = []
    if factor_scores.get("Liquidity", 100) < 50:
        _why.append(
            f"Deployable liquidity is {true_liquid_pct:.1f}% of NW "
            f"(liquid MF + deposits maturing ≤90d). Long FCNR is not treated as cash."
        )
    if factor_scores.get("Allocation", 100) < 40:
        _gap40 = max(0, 0.40 * total_networth - total_equity)
        _why.append(
            f"Equity (ex-liquid) is {equity_pct:.1f}% of NW — NRI books often run lower by design; "
            f"~{format_inr(_gap40)} more equity would reach 40%."
        )
    if factor_scores.get("Concentration", 100) < 60:
        _why.append("Top holdings concentration is elevated.")
    if factor_scores.get("Performance", 100) < 55:
        _why.append("Trailing fund performance vs Nifty50 is mixed.")
    if fcnr_pct > 0:
        _why.append(
            f"FCNR is {fcnr_pct:.1f}% of NW — USD principal + interest + INR FX vs deposit-date rate "
            f"(not the same as resident INR FD)."
        )
    if inr_fd_pct > 0:
        _why.append(f"INR FDs are {inr_fd_pct:.1f}% of NW (domestic fixed income).")
    if gold_pct > 0:
        _why.append(f"Gold is {gold_pct:.1f}% of NW (SGB + ETFs + FoFs) — diversifier, not equity.")
    if not _why:
        _why.append("No single factor is dragging hard — score is moderate overall.")
    _why_html = "".join(f"<li>{x}</li>" for x in _why)
    st.markdown(
        f'<div class="why-box"><b style="color:#e5e9f0;font-size:0.82rem">Why score is {health_score:.0f}? (NRI view)</b>'
        f'<ul style="margin:6px 0 0 0;padding-left:18px">{_why_html}</ul></div>',
        unsafe_allow_html=True,
    )

with c2:
    st.markdown('<div class="section-header">Asset allocation · NRI books</div>', unsafe_allow_html=True)
    alloc_df = pd.DataFrame({
        "Asset": ["Equity (stocks + non-liquid MF)", "Liquid MF", "INR FD", "FCNR (USD)", "Gold"],
        "Value": [total_equity, total_liquid_mf, total_inr_fd, total_fcnr, total_gold],
    })
    alloc_df = alloc_df[alloc_df["Value"] > 0].reset_index(drop=True)
    colors = ["#f59e0b", "#22c55e", "#3b82f6", "#06b6d4", "#eab308"]
    fig = px.pie(alloc_df, values="Value", names="Asset", hole=0.62, color_discrete_sequence=colors)
    fig.update_traces(textposition="inside", textinfo="percent", textfont_size=12)
    fig.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=200, showlegend=False,
                       paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6",
                       annotations=[dict(text=f"{format_inr_compact(total_networth)}<br>Net Worth",
                                         x=0.5, y=0.5, font_size=13, showarrow=False, font_color="#e5e9f0")])
    st.plotly_chart(fig, use_container_width=True, key="chart_alloc")
    # Legend with amounts (mockup-style)
    legend_items = ""
    for asset, val, col in zip(alloc_df["Asset"], alloc_df["Value"], colors):
        pct = (val / total_networth * 100) if total_networth else 0
        legend_items += (
            f'<li><span class="nm"><span style="color:{col}">●</span> {asset}</span>'
            f'<span class="amt">{pct:.1f}% · {format_inr(val)}</span></li>'
        )
    st.markdown(f'<ul class="alloc-legend">{legend_items}</ul>', unsafe_allow_html=True)

# ==================================================
# FX RETURN ATTRIBUTION — new, addresses the FCNR audit directly
# ==================================================
if not fd_valid.empty and (fd_valid["Currency"] == "USD").any():
    st.markdown('<div class="section-header">FCNR return attribution (interest + FX)</div>', unsafe_allow_html=True)
    st.caption(
        "NRI FCNR-style USD deposits: INR return = interest accrued on principal + FX from USD/INR move "
        "since each deposit's own date (cost basis at deposit-date FX, mark-to-market at today's FX)."
    )
    usd_fd = fd_valid[fd_valid["Currency"] == "USD"]
    fi1, fi2, fi3 = st.columns(3)
    fi1.metric("FCNR interest (INR)", format_inr(usd_fd["Interest Return (INR)"].sum()))
    fi2.metric("FCNR FX gain/(loss) (INR)", format_inr(total_fx_gain))
    fi3.metric("Total FCNR return (INR)", format_inr(usd_fd["Interest Return (INR)"].sum() + total_fx_gain))

# ==================================================
# HISTORY
# ==================================================
st.markdown('<div class="section-header">History</div>', unsafe_allow_html=True)
if len(history_df) < 2:
    st.caption("Building history — open this app on a few different days to see trends.")
    if not history_df.empty:
        st.dataframe(history_df.round(2), hide_index=True, use_container_width=True)
else:
    fig_hist = make_subplots(rows=1, cols=3, subplot_titles=("Net worth", "Equity % vs FD %", "Health score"))
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["net_worth"], line=dict(color="#3b82f6", width=2), showlegend=False), row=1, col=1)
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["equity_pct"], name="Equity %", line=dict(color="#22c55e", width=2)), row=1, col=2)
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["fd_pct"], name="FD %", line=dict(color="#3b82f6", width=2)), row=1, col=2)
    fig_hist.add_trace(go.Scatter(x=history_df["date"], y=history_df["health_score"], line=dict(color="#f59e0b", width=2), showlegend=False), row=1, col=3)
    fig_hist.update_layout(height=250, margin=dict(t=30, b=5, l=5, r=5), paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6", legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig_hist, use_container_width=True, key="chart_hist")
    st.dataframe(history_df.round(2), hide_index=True, use_container_width=True)
    st.download_button("Download history.csv (full precision)", history_df.to_csv(index=False), "networth_history.csv", "text/csv")

# ==================================================
# NEWS
# ==================================================
st.markdown('<div class="section-header">News pulse · Holdings + NRI</div>', unsafe_allow_html=True)

from lib.news import get_portfolio_news

stock_syms = []
if not stocks_valid.empty:
    stock_syms = stocks_valid.nlargest(6, "Current Value")["Symbol"].astype(str).tolist()

fund_names = []
if not mf_valid.empty:
    fund_names = mf_valid.nlargest(3, "Current Value")["Fund Name"].astype(str).tolist()

gold_syms = []
if not gold_valid.empty:
    gold_syms = gold_valid["Symbol"].astype(str).tolist()

st.session_state["stock_syms"] = stock_syms
st.session_state["fund_names"] = fund_names
st.session_state["gold_syms"] = gold_syms

try:
    news_items = get_portfolio_news(
        stock_symbols=stock_syms,
        fund_names=fund_names,
        gold_symbols=gold_syms,
    )
except Exception:
    news_items = []

POSITIVE = ["gain", "profit", "rise", "up", "growth", "high", "record", "beat", "strong", "surge", "rally", "jump"]
NEGATIVE = ["loss", "fall", "down", "drop", "cut", "weak", "fraud", "probe", "decline", "slash", "risk", "suit"]

def get_sentiment(title):
    t = title.lower()
    if any(w in t for w in NEGATIVE):
        return "red"
    if any(w in t for w in POSITIVE):
        return "green"
    return "neutral"

# Group by query (asset)
from collections import defaultdict
groups = defaultdict(list)
for item in news_items:
    groups[item.get("query", "General")].append(item)

if not groups:
    st.caption("No news this run.")
else:
    # Show one line per asset
    for asset, items in list(groups.items())[:8]:
        sentiments = [get_sentiment(i["title"]) for i in items]
        if "red" in sentiments:
            mark = "🔴"
            label = "Negative"
        elif "green" in sentiments:
            mark = "🟢"
            label = "Positive"
        else:
            mark = "⚪"
            label = "Neutral"

        st.markdown(f"{mark} **{asset}** — {label}")

    st.page_link("pages/4_News.py", label="View all news →", icon="📰")

st.markdown("---")

# ==================================================
# BY FAMILY MEMBER + CATEGORY MIX
# ==================================================
c3, c4 = st.columns(2)
with c3:
    st.markdown('<div class="section-header">By family member</div>', unsafe_allow_html=True)
    if owner_map:
        owner_df = pd.DataFrame([{"Owner": k, "Value": v} for k, v in owner_map.items()])
        fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s", color_discrete_sequence=["#3b82f6"])
        fig2.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=240, showlegend=False,
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
        st.plotly_chart(fig2, use_container_width=True, key="chart_owner")
with c4:
    st.markdown('<div class="section-header">Category mix (MF) — overlap proxy</div>', unsafe_allow_html=True)
    if not mf_valid.empty:
        cat_df = mf_valid.groupby("Category")["Current Value"].sum().reset_index().sort_values("Current Value", ascending=False)
        fig3 = px.bar(cat_df, x="Current Value", y="Category", orientation="h", color_discrete_sequence=["#22c55e"])
        fig3.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=240, showlegend=False,
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
        st.plotly_chart(fig3, use_container_width=True, key="chart_cat")
        st.markdown('<p class="caveat">Category-level concentration, not real stock-level overlap — genuine holdings-level overlap needs paid portfolio-disclosure data with no free equivalent.</p>', unsafe_allow_html=True)

# ==================================================
# TOP 5 STOCK CONCENTRATION + HOLDINGS SNAPSHOT
# ==================================================
snap_l, snap_r = st.columns([1, 1])
with snap_l:
    st.markdown('<div class="section-header">Top 5 stock concentration</div>', unsafe_allow_html=True)
    if not stocks_valid.empty and total_stocks > 0:
        top5 = stocks_valid.nlargest(5, "Current Value")[["Symbol", "Current Value"]].copy()
        top5_sum = top5["Current Value"].sum()
        other_val = max(total_stocks - top5_sum, 0)
        pie_df = pd.concat([
            top5.rename(columns={"Symbol": "Name", "Current Value": "Value"}),
            pd.DataFrame([{"Name": "Others", "Value": other_val}]),
        ], ignore_index=True)
        fig_t5 = px.pie(pie_df, values="Value", names="Name", hole=0.55,
                        color_discrete_sequence=["#3b82f6", "#f59e0b", "#a855f7", "#ef4444", "#22c55e", "#64748b"])
        fig_t5.update_traces(textposition="inside", textinfo="percent", textfont_size=11)
        fig_t5.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=220, showlegend=True,
                             legend=dict(orientation="h", y=-0.15, font=dict(size=10)),
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6",
                             annotations=[dict(text=f"{top5_stock_pct:.0f}%<br>Top 5", x=0.5, y=0.5,
                                               font_size=14, showarrow=False, font_color="#e5e9f0")])
        st.plotly_chart(fig_t5, use_container_width=True, key="chart_top5")
    else:
        st.caption("No stock holdings for concentration chart.")

with snap_r:
    st.markdown('<div class="section-header">Holdings snapshot · Gold</div>', unsafe_allow_html=True)
    if not gold_valid.empty:
        _g_cols = [c for c in ["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"] if c in gold_valid.columns]
        _g = gold_valid[_g_cols].copy()
        _g_height = min(360, 48 + 28 * max(len(_g), 1))
        st.dataframe(
            style_money_df(_g),
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%g"),
                "Invested": st.column_config.NumberColumn(format="₹%d"),
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "Current Price": st.column_config.NumberColumn(format="₹%.2f"),
            },
            use_container_width=True, height=_g_height, hide_index=True,
        )
        st.markdown(
            f'<p class="snap-note">Total Gold {format_inr(total_gold)} · {gold_pct:.1f}% of net worth · SGB/ETF via Groww/Yahoo · FoFs via AMFI</p>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("No gold holdings identified.")

# ==================================================
# HOLDINGS DETAIL
# ==================================================
st.markdown('<div class="section-header">Holdings detail</div>', unsafe_allow_html=True)
tab1, tab2, tab3, tab4 = st.tabs(["Mutual Funds", "Stocks", "FCNR & INR FDs", "Gold"])

with tab1:
    if not mf.empty:
        st.caption(
            f"{len(mf)} consolidated holdings — "
            f"'vs Nifty50' is a broad equity bar only (not each fund's official benchmark). "
            f"Mid/small/flexi/contra can look better or worse vs Nifty50 for the wrong reason. "
            f"'—' means insufficient history or debt-like category."
        )
        _mf_view = mf[["Owner", "Fund Name", "Category", "Current Value", "P&L", "Return %",
                        "1Y %", "3Y %", "5Y %", "vs Nifty50 1Y", "vs Nifty50 3Y", "vs Nifty50 5Y"]]
        st.dataframe(
            style_money_df(_mf_view),
            column_config={
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "1Y %": st.column_config.NumberColumn(format="%.1f%%"),
                "3Y %": st.column_config.NumberColumn(format="%.1f%%"),
                "5Y %": st.column_config.NumberColumn(format="%.1f%%"),
                "vs Nifty50 1Y": st.column_config.NumberColumn(format="%.1f%%"),
                "vs Nifty50 3Y": st.column_config.NumberColumn(format="%.1f%%"),
                "vs Nifty50 5Y": st.column_config.NumberColumn(format="%.1f%%"),
            }, use_container_width=True, height=380)

with tab2:
    if not stocks.empty:
        st.dataframe(
            style_money_df(stocks[["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"]]),
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%d"),
                "Invested": st.column_config.NumberColumn(format="₹%d"),
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "Current Price": st.column_config.NumberColumn(format="₹%.2f"),
            }, use_container_width=True, height=380)
        st.caption("Fundamental red flags (P/E, debt/equity, promoter pledging) need paid/structured data — not shown here to avoid false precision.")

with tab3:
    if not fd.empty:
        st.caption(
            "NRI view: USD rows are labeled FCNR (interest + FX vs deposit-date rate). "
            "INR rows are domestic FDs. Native currency and INR shown side by side — "
            "a FCNR is never displayed as though it were an INR deposit. Sorted by days to maturity."
        )
        _fd_cols = [c for c in [
            "Holder Name", "Product", "Currency", "Principal (Native)", "Principal (INR, at deposit FX)",
            "ROI %", "Days to Maturity", "Current Value (Native)", "Current Value (INR)",
            "Interest Return (INR)", "FX Gain/Loss (INR)", "Maturity Date",
        ] if c in fd.columns]
        _fd_view = fd[_fd_cols].copy()
        if "Days to Maturity" in _fd_view.columns:
            _fd_view = _fd_view.sort_values("Days to Maturity", ascending=True, na_position="last")
        st.dataframe(
            style_money_df(_fd_view, pnl_cols=("FX Gain/Loss (INR)", "Interest Return (INR)")),
            column_config={
                "Principal (Native)": st.column_config.NumberColumn(format="%.2f"),
                "Principal (INR, at deposit FX)": st.column_config.NumberColumn(format="₹%d"),
                "Current Value (Native)": st.column_config.NumberColumn(format="%.2f"),
                "Current Value (INR)": st.column_config.NumberColumn(format="₹%d"),
                "Interest Return (INR)": st.column_config.NumberColumn(format="₹%d"),
                "FX Gain/Loss (INR)": st.column_config.NumberColumn(format="₹%d"),
                "ROI %": st.column_config.NumberColumn(format="%.2f%%"),
            }, use_container_width=True, height=380)
        st.markdown(
            f'<p class="snap-note">FCNR {format_inr(total_fcnr)} ({fcnr_pct:.1f}%) · '
            f'INR FD {format_inr(total_inr_fd)} ({inr_fd_pct:.1f}%) · '
            f'Deployable liquidity (liquid MF + ≤90d deposits) {format_inr(total_true_liquid)} ({true_liquid_pct:.1f}%)</p>',
            unsafe_allow_html=True,
        )

with tab4:
    if not gold.empty:
        st.caption(
            "Unified Gold book: Sovereign Gold Bonds (SGB…-GB), gold ETFs (e.g. GOLDBEES), and Gold ETF FoFs. "
            "Same rows as the Gold snapshot above — excluded from Stocks and Mutual Funds so gold appears in one book only. "
            "SGB maturity/interest are not invented — source file does not carry them."
        )
        _g_tab_cols = [c for c in ["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"] if c in gold.columns]
        _g_tab = gold[_g_tab_cols]
        _g_tab_h = min(400, 48 + 28 * max(len(_g_tab), 1))
        st.dataframe(
            style_money_df(_g_tab),
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%g"),
                "Invested": st.column_config.NumberColumn(format="₹%d"),
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "Current Price": st.column_config.NumberColumn(format="₹%.2f"),
            }, use_container_width=True, height=_g_tab_h, hide_index=True)
        st.markdown(
            f'<p class="snap-note">Total Gold {format_inr(total_gold)} · {gold_pct:.1f}% of net worth</p>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("No gold holdings identified in the current data.")

st.markdown("---")
src = "AMFI live" if (len(amfi_navs) and not amfi_cache_date) else (f"AMFI cache {amfi_cache_date}" if amfi_cache_date else "AMFI offline")
_usd_lbl = ("%.2f" % usd_inr) if usd_inr else "n/a"
_footer = (
    "INR · USD "
    + _usd_lbl
    + " · "
    + now_ist.strftime("%d %b %Y %H:%M IST")
    + " · "
    + src
    + " (%d schemes) · Stocks/Gold ETF: Groww+Yahoo · Gold FoF: AMFI · Gold Rs/10g: goldprice.dev" % len(amfi_navs)
)
st.caption(_footer)

# ----- Pass matured FD amount to Deep Health -----
try:
    if "attention_flags" in dir() or "flags" in dir():
        pass  # placeholder
    # Simple heuristic: look for any variable that looks like matured FD value
    for varname in ["matured_fd_value", "fd_matured_amount", "uncollected_fd"]:
        if varname in dir() and globals().get(varname):
            st.session_state["matured_fd_amount"] = float(globals()[varname])
            break
    # Fallback: if you store attention items as text, skip for now
except Exception:
    pass
