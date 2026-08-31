import requests
import pandas as pd
import streamlit as st
from datetime import timedelta
import re

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
        r = requests.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=15)
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
        metrics[f"cagr_{label}"] = calc_cagr(past.iloc[-1]["nav"], end_nav, years) if not past.empty else None
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
    if not name: return ""
    name = re.sub(r"[-–]\s*Direct.*", "", str(name), flags=re.I)
    name = re.sub(r"[-–]\s*Regular.*", "", name, flags=re.I)
    name = re.sub(r"\bDirect\b.*|\bGrowth\b.*|\bPlan\b|\bOption\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -")


MANUAL_CODES = {
    "sbi contra": 119598,
    "invesco india small cap": 120603,
    "kotak hybrid equity": 119551,
    "kotak infrastructure": 119713,
    "hdfc liquid": 119062,
    "parag parikh liquid": 143269,
}


def match_scheme_code(fund_name: str):
    if not fund_name: return None, {}
    lower = fund_name.lower()
    for key, code in MANUAL_CODES.items():
        if key in lower:
            return code, {"schemeName": fund_name, "schemeCode": code}

    candidates = [fund_name, clean_name(fund_name)]
    words = clean_name(fund_name).split()
    if len(words) >= 3:
        candidates += [" ".join(words[:4]), " ".join(words[:3])]

    seen, best = set(), None
    for q in candidates:
        if len(q) < 4: continue
        for r in search_scheme(q):
            code = r.get("schemeCode")
            name = r.get("schemeName", "").lower()
            if code in seen: continue
            seen.add(code)
            if "direct" in name and "growth" in name:
                return code, r
            if best is None:
                best = (code, r)
    return best if best else (None, {})


@st.cache_data(ttl=1800, show_spinner=False)
def analyze_fund(fund_name: str, current_value: float = 0, weight_pct: float = 0):
    code, _ = match_scheme_code(fund_name)
    if not code:
        return {"fund_name": fund_name, "status": "not_found", "message": "Could not find scheme code"}
    nav_df, meta = get_nav_history(code)
    metrics = compute_metrics(nav_df)
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
    """Fund-specific + market keywords."""
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
        flags = []
        keywords = [
            "manager", "resign", "takes over", "strategy", "sebi",
            "outflow", "underperform", "crash", "fall", "surge", "rally", "slump"
        ]
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                title = entry.get("title", "")
                if any(k in title.lower() for k in keywords):
                    flags.append(title[:100])
        # dedup
        seen = set()
        unique = []
        for f in flags:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique[:5]
    except Exception:
        return []


# ---------- Experimental holdings (mfdata.in) ----------
@st.cache_data(ttl=86400, show_spinner=False)
def try_fetch_holdings(scheme_code: int):
    """Best-effort holdings. Returns list of {name, weight} or empty."""
    try:
        # mfdata.in family/holdings style (may change)
        r = requests.get(
            f"https://mfdata.in/api/v1/schemes/{scheme_code}",
            timeout=10,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        # try common shapes
        holdings = data.get("data", {}).get("holdings") or data.get("holdings") or []
        out = []
        for h in holdings[:15]:
            name = h.get("name") or h.get("stock_name") or h.get("instrument")
            w = h.get("weight_pct") or h.get("weight") or h.get("pct")
            if name and w is not None:
                out.append({"name": str(name), "weight": float(w)})
        return out
    except Exception:
        return []
