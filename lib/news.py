from __future__ import annotations
import urllib.parse
import feedparser
import streamlit as st
from datetime import datetime, timedelta, timezone

NRI_QUERIES = [
    "NRI tax India",
    "NRI taxation FEMA",
    "FCNR interest tax",
    "RBI NRI",
    "NRE NRO account rules",
    "budget NRI India",
]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_news_for(queries: list[str], max_items: int = 12, days: int = 45) -> list[dict]:
    """Google News RSS — personal use. Cached 5 min so auto-refresh helps."""
    items = []
    seen = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode({"q": q, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
        )
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:8]:
                link = getattr(e, "link", "") or ""
                title = getattr(e, "title", "") or ""
                key = (title[:80], link[:80])
                if key in seen:
                    continue
                published = None
                if getattr(e, "published_parsed", None):
                    try:
                        published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                        if published < cutoff:
                            continue
                    except Exception:
                        published = None
                seen.add(key)
                items.append({
                    "title": title,
                    "link": link,
                    "source": getattr(e, "source", {}).get("title", "") if isinstance(getattr(e, "source", None), dict) else "",
                    "published": published.strftime("%d %b %Y") if published else "",
                    "query": q,
                })
        except Exception:
            continue
    # Prefer NRI/tax items first, then by presence of published
    def sort_key(x):
        is_nri = 0 if x["query"] in NRI_QUERIES else 1
        return (is_nri, x.get("published") or "")
    items.sort(key=sort_key)
    return items[:max_items]

def build_news_queries(stock_symbols: list[str], fund_names: list[str], gold_symbols: list[str]) -> list[str]:
    qs = []
    qs.extend(stock_symbols[:5])
    for n in fund_names[:4]:
        short = str(n).split(" - ")[0].split(" FUND")[0].strip()
        if short:
            qs.append(short)
    for sym in gold_symbols:
        u = str(sym).upper()
        if "SGB" in u:
            qs.append("Sovereign Gold Bond")
        elif "GOLD" in u:
            qs.append("Gold ETF India")
        else:
            qs.append(sym)
    qs.extend(NRI_QUERIES)
    # dedupe
    out, seen = [], set()
    for q in qs:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(q.strip())
    return out
