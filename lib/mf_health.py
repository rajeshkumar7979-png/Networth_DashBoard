import requests
import pandas as pd
import streamlit as st
from datetime import timedelta
import re
from collections import defaultdict

@st.cache_data(ttl=3600, show_spinner=False)
def search_scheme(name: str, limit: int = 10):
    try:
        r = requests.get("https://api.mfapi.in/mf/search", params={"q": name}, timeout=12)
        data = r.json()
        if isinstance(data, list):
            return data[:limit]
    except Exception:
        pass
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_nav_history(scheme_code: int):
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{int(scheme_code)}", timeout=15)
        data = r.json()
        if data.get("status") == "SUCCESS" and data.get("data"):
            df = pd.DataFrame(data["data"])
            df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
            df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
            df = df.dropna().sort_values("date")
            return df, data.get("meta", {})
    except Exception:
        pass
    return pd.DataFrame(), {}


def calc_cagr(start_nav, end_nav, years):
    if start_nav <= 0 or years <= 0:
        return None
    return (end_nav / start_nav) ** (1 / years) - 1


def max_drawdown(nav_series):
    if len(nav_series) < 5:
        return None
    peak = nav_series.cummax()
    dd = (nav_series - peak) / peak
    return float(dd.min())


def compute_metrics(nav_df: pd.DataFrame):
    if nav_df.empty or len(nav_df) < 30:
        return {}
    nav_df = nav_df.sort_values("date")
    latest = nav_df.iloc[-1]
    end_nav, end_date = latest["nav"], latest["date"]
    metrics = {"latest_nav": end_nav, "latest_date": end_date.strftime("%Y-%m-%d")}
    for years, label in [(1, "1Y"), (3, "3Y"), (5, "5Y")]:
        target = end_date - timedelta(days=int(365.25 * years))
        past = nav_df[nav_df["date"] <= target]
        metrics[f"cagr_{label}"] = (
            calc_cagr(past.iloc[-1]["nav"], end_nav, years) if not past.empty else None
        )
    metrics["max_drawdown"] = max_drawdown(nav_df["nav"])
    return metrics


def simple_health_score(metrics, weight_pct=0):
    score = 55
    cagr3 = metrics.get("cagr_3Y")
    if cagr3 is not None:
        if cagr3 > 0.15: score += 15
        elif cagr3 > 0.10: score += 8
        elif cagr3 < 0.05: score -= 12
    dd = metrics.get("max_drawdown")
    if dd is not None:
        if dd < -0.40: score -= 20
        elif dd < -0.30: score -= 12
        elif dd > -0.18: score += 6
    if weight_pct > 25: score -= 15
    elif weight_pct > 15: score -= 8
    return max(0, min(100, int(score)))


def clean_name(name: str) -> str:
    if not name:
        return ""
    name = re.sub(r"[-–]\s*Direct.*", "", str(name), flags=re.I)
    name = re.sub(r"[-–]\s*Regular.*", "", name, flags=re.I)
    name = re.sub(r"\bDirect\b.*|\bGrowth\b.*|\bPlan\b|\bOption\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -")


# Manual overrides (name fragment → AMFI code)
MANUAL_CODES = {
    "sbi contra": 119598,
    "invesco india small cap": 120603,
    "kotak hybrid equity": 119551,
    "kotak infrastructure": 119713,
    "hdfc liquid": 119062,
    "parag parikh liquid": 143269,
    "hdfc mid cap": 118955,
    "uti nifty next 50": 120716,
    "icici prudential bharat 22": 143903,
    "hdfc large cap": 102000,
    "edelweiss mid cap": 140175,
    "quant small cap": 120828,
    "parag parikh flexi": 122639,
}


def match_scheme_code(fund_name: str):
    if not fund_name:
        return None, {}
    lower = fund_name.lower()
    for key, code in MANUAL_CODES.items():
        if key in lower:
            return int(code), {"schemeName": fund_name, "schemeCode": code}

    candidates = [fund_name, clean_name(fund_name)]
    words = clean_name(fund_name).split()
    if len(words) >= 3:
        candidates += [" ".join(words[:4]), " ".join(words[:3])]

    seen, best = set(), None
    for q in candidates:
        if len(q) < 4:
            continue
        for r in search_scheme(q):
            code = r.get("schemeCode")
            name = (r.get("schemeName") or "").lower()
            if code in seen:
                continue
            seen.add(code)
            if "direct" in name and "growth" in name:
                return int(code), r
            if best is None:
                best = (int(code), r)
    return best if best else (None, {})


@st.cache_data(ttl=1800, show_spinner=False)
def analyze_fund(fund_name: str, current_value: float = 0, weight_pct: float = 0):
    code, _ = match_scheme_code(fund_name)
    if not code:
        return {
            "fund_name": fund_name,
            "status": "not_found",
            "message": "Name matching failed — add to MANUAL_CODES",
            "scheme_code": None,
        }
    nav_df, meta = get_nav_history(code)
    metrics = compute_metrics(nav_df)
        if not metrics:
        return {
            "fund_name": fund_name,
            "status": "no_metrics",
            "message": "Scheme code found but NAV history empty",
            "scheme_code": code,
            "meta": meta,
            "current_value": current_value,
            "weight_pct": weight_pct,
        }
            "message": "Scheme code found but NAV/returns empty",
            "scheme_code": code,
            "meta": meta,
            "current_value": current_value,
            "weight_pct": weight_pct,
        }
    return {
        "fund_name": fund_name,
        "scheme_code": code,
        "meta": meta,
        "metrics": metrics,
        "health_score": simple_health_score(metrics, weight_pct),
        "current_value": current_value,
        "weight_pct": weight_pct,
        "status": "ok",
    }


def get_news_flags(fund_name: str):
    try:
        import feedparser
        queries = [
            clean_name(fund_name) + " mutual fund",
            "Nifty 50",
            "Sensex",
            "Indian markets",
            "gold price India",
            "silver price India",
        ]
        keywords = [
            "manager", "resign", "takes over", "strategy", "sebi",
            "outflow", "underperform", "crash", "fall", "surge", "rally", "slump", "down",
        ]
        flags = []
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                title = entry.get("title", "")
                if any(k in title.lower() for k in keywords):
                    flags.append(title[:110])
        seen, unique = set(), []
        for f in flags:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique[:5]
    except Exception:
        return []


# ---------- Holdings via mfdata.in (best-effort) ----------
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_holdings_mfdata(scheme_code: int):
    """Return list of {name, weight_pct} or []."""
    try:
        # Try scheme endpoint first
        r = requests.get(f"https://mfdata.in/api/v1/schemes/{int(scheme_code)}", timeout=12)
        if r.status_code == 200:
            data = r.json().get("data") or r.json()
            # common shapes
            for key in ("holdings", "equity_holdings", "portfolio"):
                h = data.get(key) if isinstance(data, dict) else None
                if h:
                    return _normalize_holdings(h)
        # Try family-style if scheme has family_id
        fam = None
        if isinstance(data, dict):
            fam = data.get("family_id") or data.get("family")
        if fam:
            r2 = requests.get(f"https://mfdata.in/api/v1/families/{fam}/holdings", timeout=12)
            if r2.status_code == 200:
                d2 = r2.json().get("data") or r2.json()
                eq = d2.get("equity") or d2.get("equity_holdings") or d2
                return _normalize_holdings(eq)
    except Exception:
        pass
    return []


def _normalize_holdings(raw):
    out = []
    if not raw:
        return out
    if isinstance(raw, dict):
        raw = raw.get("equity") or raw.get("holdings") or []
    for h in raw:
        if not isinstance(h, dict):
            continue
        name = h.get("name") or h.get("stock_name") or h.get("instrument") or h.get("security")
        w = h.get("weight_pct") or h.get("weight") or h.get("pct") or h.get("percentage")
        if name and w is not None:
            try:
                out.append({"name": str(name).strip(), "weight": float(w)})
            except Exception:
                continue
    return out[:20]
