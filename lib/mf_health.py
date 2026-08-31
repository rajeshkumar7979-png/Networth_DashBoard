import requests
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
from difflib import get_close_matches

# ---------- Helpers ----------
@st.cache_data(ttl=3600, show_spinner=False)
def search_scheme(name: str, limit: int = 5):
    """Search mfapi.in for scheme code by name."""
    try:
        r = requests.get(
            "https://api.mfapi.in/mf/search",
            params={"q": name},
            timeout=10,
        )
        data = r.json()
        if isinstance(data, list):
            return data[:limit]
    except Exception:
        pass
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_nav_history(scheme_code: int):
    """Full NAV history from mfapi.in."""
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=15)
        data = r.json()
        if data.get("status") == "SUCCESS" and data.get("data"):
            df = pd.DataFrame(data["data"])
            df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
            df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
            df = df.dropna().sort_values("date")
            meta = data.get("meta", {})
            return df, meta
    except Exception:
        pass
    return pd.DataFrame(), {}


def calc_cagr(start_nav, end_nav, years):
    if start_nav <= 0 or years <= 0:
        return None
    return (end_nav / start_nav) ** (1 / years) - 1


def max_drawdown(nav_series):
    if len(nav_series) < 2:
        return None
    peak = nav_series.cummax()
    dd = (nav_series - peak) / peak
    return dd.min()


def compute_metrics(nav_df: pd.DataFrame):
    """Return 1Y/3Y/5Y CAGR + max drawdown."""
    if nav_df.empty or len(nav_df) < 30:
        return {}

    nav_df = nav_df.sort_values("date")
    latest = nav_df.iloc[-1]
    end_nav = latest["nav"]
    end_date = latest["date"]

    metrics = {"latest_nav": end_nav, "latest_date": end_date.strftime("%Y-%m-%d")}

    for years, label in [(1, "1Y"), (3, "3Y"), (5, "5Y")]:
        target = end_date - timedelta(days=int(365.25 * years))
        past = nav_df[nav_df["date"] <= target]
        if not past.empty:
            start_nav = past.iloc[-1]["nav"]
            cagr = calc_cagr(start_nav, end_nav, years)
            metrics[f"cagr_{label}"] = cagr
        else:
            metrics[f"cagr_{label}"] = None

    metrics["max_drawdown"] = max_drawdown(nav_df["nav"])
    return metrics


def simple_health_score(metrics: dict, weight_pct: float = 0):
    """Very simple 0-100 score."""
    score = 50
    # Returns boost
    cagr3 = metrics.get("cagr_3Y")
    if cagr3 is not None:
        if cagr3 > 0.15:
            score += 15
        elif cagr3 > 0.10:
            score += 8
        elif cagr3 < 0.05:
            score -= 10

    # Drawdown penalty
    dd = metrics.get("max_drawdown")
    if dd is not None:
        if dd < -0.35:
            score -= 20
        elif dd < -0.25:
            score -= 10
        elif dd > -0.15:
            score += 5

    # Concentration penalty
    if weight_pct > 25:
        score -= 15
    elif weight_pct > 15:
        score -= 8

    return max(0, min(100, int(score)))


def match_scheme_code(fund_name: str):
    """Best-effort match from fund name to scheme code."""
    results = search_scheme(fund_name)
    if not results:
        # try shorter name
        short = fund_name.split(" - ")[0].split(" FUND")[0]
        results = search_scheme(short)

    if not results:
        return None, {}

    # Prefer Direct + Growth
    for r in results:
        name = r.get("schemeName", "").lower()
        if "direct" in name and "growth" in name:
            return r.get("schemeCode"), r

    return results[0].get("schemeCode"), results[0]


@st.cache_data(ttl=1800, show_spinner=False)
def analyze_fund(fund_name: str, current_value: float = 0, weight_pct: float = 0):
    """Full light analysis for one fund."""
    code, raw = match_scheme_code(fund_name)
    if not code:
        return {
            "fund_name": fund_name,
            "status": "not_found",
            "message": "Could not find scheme code",
        }

    nav_df, meta = get_nav_history(code)
    metrics = compute_metrics(nav_df)
    score = simple_health_score(metrics, weight_pct)

    return {
        "fund_name": fund_name,
        "scheme_code": code,
        "meta": meta,
        "metrics": metrics,
        "health_score": score,
        "current_value": current_value,
        "weight_pct": weight_pct,
        "status": "ok",
    }
