import feedparser
import streamlit as st
from datetime import datetime, timedelta
import re

NRI_QUERIES = [
    "NRI tax India",
    "NRI taxation",
    "FCNR interest",
    "FEMA NRI",
    "RBI NRI",
    "NRI mutual fund",
    "repatriation NRI",
    "NRE NRO account",
    "NRI investment rules",
]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_news_for(queries, max_items=12):
    """Fetch news from Google News RSS for the given queries."""
    if not queries:
        return []

    all_items = []
    seen_titles = set()

    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                published = ""
                if hasattr(entry, "published"):
                    published = entry.published
                elif hasattr(entry, "updated"):
                    published = entry.updated

                all_items.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": published,
                    "source": entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
                    "query": q,
                })
        except Exception:
            continue

    # Keep only roughly last 45 days if date parsing works
    cutoff = datetime.now() - timedelta(days=45)
    filtered = []
    for item in all_items:
        filtered.append(item)

    return filtered[:max_items]


def get_portfolio_news(stock_symbols=None, fund_names=None, gold_symbols=None):
    """Build query list from holdings + NRI queries and fetch news."""
    queries = []

    if stock_symbols:
        queries.extend([str(s) for s in stock_symbols[:5] if s])

    if fund_names:
        for name in fund_names[:4]:
            short = str(name).split(" - ")[0].split(" FUND")[0].strip()
            if short:
                queries.append(short)

    if gold_symbols:
        for sym in gold_symbols:
            s = str(sym).upper()
            if "SGB" in s:
                queries.append("Sovereign Gold Bond")
            elif "GOLD" in s:
                queries.append("Gold ETF India")

    # Always add NRI / tax / rules queries
    queries.extend(NRI_QUERIES)

    # Deduplicate
    seen = set()
    unique = []
    for q in queries:
        qn = q.strip().lower()
        if qn and qn not in seen:
            seen.add(qn)
            unique.append(q.strip())

    return fetch_news_for(unique)
