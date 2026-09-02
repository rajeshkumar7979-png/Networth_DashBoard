import requests
import pandas as pd
import streamlit as st
from datetime import timedelta, datetime
import re
import os
import json

HOLDINGS_CACHE_PATH = "data/mf_holdings_cache.json"


# ---------- NAV history (fallback only — used only when Command Center didn't ----------
# ---------- already compute returns for this fund, e.g. Liquid/debt-like funds) ----------
@st.cache_data(ttl=21600, show_spinner=False)
def get_nav_history(scheme_code: int):
    """Same source + same permissive parse as Command Center's get_mf_nav_history."""
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{int(scheme_code)}", timeout=12)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data") or []
        if not data:
            return pd.DataFrame(), payload.get("meta", {})
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna().sort_values("date")
        if df.empty:
            return pd.DataFrame(), payload.get("meta", {})
        return df, payload.get("meta", {})
    except Exception:
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
    val = float(dd.min())
    if val < -0.80:
        return None  # treat as bad data rather than display a false extreme
    return val


def compute_metrics(nav_df: pd.DataFrame):
    if nav_df.empty or len(nav_df) < 10:
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
    if not name:
        return ""
    name = re.sub(r"[-–]\s*Direct.*", "", str(name), flags=re.I)
    name = re.sub(r"[-–]\s*Regular.*", "", name, flags=re.I)
    name = re.sub(r"\bDirect\b.*|\bGrowth\b.*|\bPlan\b|\bOption\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -")


# ---------- Core analysis — reuses Command Center's returns; never re-guesses identity ----------
@st.cache_data(ttl=1800, show_spinner=False)
def analyze_fund(
    fund_name: str,
    current_value: float = 0,
    weight_pct: float = 0,
    scheme_code=None,
    cagr_1y=None,
    cagr_3y=None,
    cagr_5y=None,
    latest_nav=None,
):
    """
    scheme_code, cagr_1y/3y/5y (as % values, e.g. 12.3) and latest_nav come
    from Command Center — already resolved via the AMFI map and already
    computed once. This function reuses them directly and does NOT call
    mfapi.in again for any fund Command Center already has numbers for.
    It only fetches independently as a fallback (e.g. Liquid/debt-like funds
    Command Center doesn't benchmark).
    """
    code = None
    try:
        if scheme_code is not None and str(scheme_code).strip() not in ("", "None", "nan"):
            code = int(float(scheme_code))
    except Exception:
        code = None

    if not code:
        return {
            "fund_name": fund_name,
            "status": "not_found",
            "message": "No AMFI code from Command Center",
            "scheme_code": None,
        }

    have_returns = any(v is not None for v in (cagr_1y, cagr_3y, cagr_5y))
    if have_returns:
        metrics = {
            "cagr_1Y": (cagr_1y / 100) if cagr_1y is not None else None,
            "cagr_3Y": (cagr_3y / 100) if cagr_3y is not None else None,
            "cagr_5Y": (cagr_5y / 100) if cagr_5y is not None else None,
            "latest_nav": latest_nav,
            "latest_date": "",
            "max_drawdown": None,  # Command Center doesn't compute this — not invented here
        }
        return {
            "fund_name": fund_name,
            "scheme_code": code,
            "meta": {},
            "metrics": metrics,
            "health_score": simple_health_score(metrics, weight_pct),
            "current_value": current_value,
            "weight_pct": weight_pct,
            "status": "ok",
        }

    # Fallback: only reached when Command Center passed no returns at all for this fund
    nav_df, meta = get_nav_history(code)
    metrics = compute_metrics(nav_df)
    if not metrics or metrics.get("latest_nav") in (None, 0):
        return {
            "fund_name": fund_name,
            "status": "no_metrics",
            "message": "History n/a on mfapi — same limit as Command Center",
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
            "Nifty 50", "Sensex", "Indian markets", "gold price India", "silver price India",
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


# ---------- Holdings / overlap — monthly-cadence cache (unchanged) ----------
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
    return out


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
                raw = entry.get("top_holdings") or entry.get("holdings") or entry.get("equity_holdings") or []
                out[int(code)] = _normalize_holdings(raw)
        except Exception:
            continue
    return out
def get_holdings_for_funds(codes, force_refresh=False):
    """
    Load complete mutual-fund holdings.

    Supports:
      - New cache format:
        {"scheme_code": [holding, holding, ...]}

      - Old cache format:
        {"scheme_code": {"holdings": [holding, ...]}}

    The function never assumes one cache structure.
    """

    result = {}
    cache = {}

    # ---------------------------------------------------------
    # LOAD CACHE
    # ---------------------------------------------------------
    try:
        if os.path.exists(HOLDINGS_CACHE_PATH):
            with open(HOLDINGS_CACHE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            if isinstance(loaded, dict):
                cache = loaded

    except Exception:
        cache = {}

    # ---------------------------------------------------------
    # READ CACHED HOLDINGS
    # ---------------------------------------------------------
    missing_codes = []

    for raw_code in codes:

        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            continue

        key = str(code)

        entry = cache.get(key)

        holdings = None

        # NEW FORMAT
        if isinstance(entry, list):
            holdings = entry

        # OLD FORMAT
        elif isinstance(entry, dict):

            holdings = entry.get("holdings")

            if not isinstance(holdings, list) or not holdings:
                holdings = entry.get("top_holdings")

            if not isinstance(holdings, list) or not holdings:
                holdings = entry.get("equity_holdings")

            if not isinstance(holdings, list) or not holdings:
                holdings = entry.get("portfolio")

        # Valid cached holdings
        if isinstance(holdings, list) and len(holdings) > 0:
            result[code] = holdings
        else:
            missing_codes.append(code)

    # ---------------------------------------------------------
    # FORCE REFRESH
    # ---------------------------------------------------------
    if force_refresh:
        missing_codes = []

        for raw_code in codes:
            try:
                code = int(raw_code)
                if code not in missing_codes:
                    missing_codes.append(code)
            except (TypeError, ValueError):
                continue

    # ---------------------------------------------------------
    # LIVE FETCH FOR MISSING FUNDS
    # ---------------------------------------------------------
    if missing_codes:

        try:
            fresh = fetch_holdings_batch_live(missing_codes)

        except Exception:
            fresh = {}

        if isinstance(fresh, dict):

            for raw_code in missing_codes:

                try:
                    code = int(raw_code)
                except (TypeError, ValueError):
                    continue

                entry = fresh.get(code)

                if entry is None:
                    entry = fresh.get(str(code))

                holdings = None

                # New live response
                if isinstance(entry, list):
                    holdings = entry

                # Dictionary response
                elif isinstance(entry, dict):

                    holdings = entry.get("holdings")

                    if not isinstance(holdings, list) or not holdings:
                        holdings = entry.get("top_holdings")

                    if not isinstance(holdings, list) or not holdings:
                        holdings = entry.get("equity_holdings")

                    if not isinstance(holdings, list) or not holdings:
                        holdings = entry.get("portfolio")

                if isinstance(holdings, list) and len(holdings) > 0:

                    result[code] = holdings

                    # Always save in the NEW format
                    cache[str(code)] = holdings

    # ---------------------------------------------------------
    # SAVE UPDATED CACHE
    # ---------------------------------------------------------
    try:

        os.makedirs(
            os.path.dirname(HOLDINGS_CACHE_PATH),
            exist_ok=True
        )

        with open(
            HOLDINGS_CACHE_PATH,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                cache,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception:
        pass

    return result


