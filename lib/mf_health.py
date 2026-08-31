import requests
import pandas as pd
import streamlit as st
from datetime import timedelta, datetime
import re
import os
import json


HOLDINGS_CACHE_PATH = "data/mf_holdings_cache.json"


@st.cache_data(ttl=3600, show_spinner=False)
def search_scheme(name: str, limit: int = 10):
    try:
        r = requests.get(
            "https://api.mfapi.in/mf/search",
            params={"q": name},
            timeout=12,
        )
        data = r.json()
        if isinstance(data, list):
            return data[:limit]
    except Exception:
        pass
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_nav_history(scheme_code: int):
    try:
        r = requests.get(
            f"https://api.mfapi.in/mf/{int(scheme_code)}",
            timeout=15,
        )
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
    end_nav = latest["nav"]
    end_date = latest["date"]
    metrics = {
        "latest_nav": end_nav,
        "latest_date": end_date.strftime("%Y-%m-%d"),
    }
    for years, label in [(1, "1Y"), (3, "3Y"), (5, "5Y")]:
        target = end_date - timedelta(days=int(365.25 * years))
        past = nav_df[nav_df["date"] <= target]
        if not past.empty:
            metrics[f"cagr_{label}"] = calc_cagr(past.iloc[-1]["nav"], end_nav, years)
        else:
            metrics[f"cagr_{label}"] = None
    metrics["max_drawdown"] = max_drawdown(nav_df["nav"])
    return metrics


def simple_health_score(metrics, weight_pct=0):
    score = 55
    cagr3 = metrics.get("cagr_3Y")
    if cagr3 is not None:
        if cagr3 > 0.15:
            score += 15
        elif cagr3 > 0.10:
            score += 8
        elif cagr3 < 0.05:
            score -= 12
    dd = metrics.get("max_drawdown")
    if dd is not None:
        if dd < -0.40:
            score -= 20
        elif dd < -0.30:
            score -= 12
        elif dd > -0.18:
            score += 6
    if weight_pct > 25:
        score -= 15
    elif weight_pct > 15:
        score -= 8
    return max(0, min(100, int(score)))


def clean_name(name: str) -> str:
    if not name:
        return ""
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

    seen = set()
    best = None
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
            "message": "Name matching failed",
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
            "outflow", "underperform", "crash", "fall", "surge",
            "rally", "slump", "down",
        ]
        flags = []
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                title = entry.get("title", "")
                if any(k in title.lower() for k in keywords):
                    flags.append(title[:110])
        seen = set()
        unique = []
        for f in flags:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique[:5]
    except Exception:
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
        name = (
            h.get("name")
            or h.get("stock_name")
            or h.get("instrument")
            or h.get("security")
        )
        w = (
            h.get("weight_pct")
            or h.get("weight")
            or h.get("pct")
            or h.get("percentage")
        )
        if name and w is not None:
            try:
                out.append({"name": str(name).strip(), "weight": float(w)})
            except Exception:
                continue
    return out[:20]


def _load_holdings_cache():
    try:
        if not os.path.exists(HOLDINGS_CACHE_PATH):
            return {}
        with open(HOLDINGS_CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_holdings_cache(cache: dict):
    try:
        os.makedirs("data", exist_ok=True)
        with open(HOLDINGS_CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _is_stale(entry: dict, max_age_days: int = 35) -> bool:
    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
        return (datetime.now() - fetched).days > max_age_days
    except Exception:
        return True


def fetch_holdings_batch_live(scheme_codes: list, timeout=30):
    out = {}
    codes = [int(c) for c in scheme_codes if c]
    for i in range(0, len(codes), 10):
        chunk = codes[i:i + 10]
        try:
            r = requests.get(
                "https://mfdata.in/api/v1/compare",
                params={"scheme_codes": ",".join(str(c) for c in chunk)},
                timeout=timeout,
            )
            if r.status_code != 200:
                continue
            payload = r.json()
            data = payload.get("data") or payload
            entries = data if isinstance(data, list) else data.get("schemes", [])
            for entry in entries:
                code = entry.get("scheme_code") or entry.get("code")
                if code is None:
                    continue
                raw = (
                    entry.get("top_holdings")
                    or entry.get("holdings")
                    or entry.get("equity_holdings")
                    or []
                )
                out[int(code)] = _normalize_holdings(raw)
        except Exception:
            continue
    return out


def get_holdings_for_funds(scheme_codes: list, force_refresh: bool = False):
    """
    Monthly-cadence cache.
    Only calls mfdata.in for missing or >35-day-old entries.
    On failure, still serves last-known-good cache.
    """
    cache = _load_holdings_cache()
    result = {}
    to_fetch = []

    for code in scheme_codes:
        key = str(code)
        entry = cache.get(key)
        if entry and not _is_stale(entry) and not force_refresh:
            result[int(code)] = entry["holdings"]
        else:
            to_fetch.append(int(code))

    if to_fetch:
        fresh = fetch_holdings_batch_live(to_fetch)
        now_iso = datetime.now().isoformat()
        for code in to_fetch:
            key = str(code)
            if code in fresh and fresh[code]:
                cache[key] = {"holdings": fresh[code], "fetched_at": now_iso}
                result[code] = fresh[code]
            elif key in cache:
                result[code] = cache[key]["holdings"]
        _save_holdings_cache(cache)

    return result, cache
