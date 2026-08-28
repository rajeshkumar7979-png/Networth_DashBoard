import feedparser
import streamlit as st
from datetime import datetime, timedelta

NRI_QUERIES = [
    "NRI tax India",
    "NRI taxation",
    "FCNR interest",
    "FEMA NRI",
    "RBI NRI",
    "NRI mutual fund",
    "repatriation NRI",
    "NRE NRO account",
]

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_one(query, limit=4):
    items = []
    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": getattr(entry, "published", "") or getattr(entry, "updated", ""),
                "source": entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
                "query": query,
            })
    except Exception:
        pass
    return items


def get_portfolio_news(stock_symbols=None, fund_names=None, gold_symbols=None):
    """Balanced news: few items per holding + NRI queries."""
    queries = []

    # Holdings (limit how many we ask for)
    if stock_symbols:
        queries.extend([str(s) for s in stock_symbols[:6] if s])
    if fund_names:
        for name in fund_names[:3]:
            short = str(name).split(" - ")[0].split(" FUND")[0].strip()
            if short:
                queries.append(short)
    if gold_symbols:
        queries.append("Sovereign Gold Bond")
        queries.append("Gold ETF India")

    # Always add NRI / tax
    queries.extend(NRI_QUERIES)

    # Deduplicate
    seen = set()
    unique_queries = []
    for q in queries:
        qn = q.strip().lower()
        if qn and qn not in seen:
            seen.add(qn)
            unique_queries.append(q.strip())

    all_items = []
    seen_titles = set()

    for q in unique_queries:
        # Only 2–3 news per query so one stock cannot flood
        batch = _fetch_one(q, limit=3)
        for item in batch:
            t = item["title"]
            if t not in seen_titles:
                seen_titles.add(t)
                all_items.append(item)

    return all_items
