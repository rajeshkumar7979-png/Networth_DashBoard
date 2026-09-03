import re
import feedparser
import streamlit as st
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Query sets — kept separate on purpose:
#   NRI_TAX_QUERIES   -> genuinely NRI/FEMA/tax-specific, the differentiator
#                        content for this app. Never crowded out by holdings.
#   MACRO_QUERIES     -> broad market pulse (Nifty/Sensex/gold/silver). Useful
#                        context, but not holding-specific and not NRI-specific.
# ---------------------------------------------------------------------------
NRI_TAX_QUERIES = [
    "NRI tax India",
    "NRI taxation",
    "FCNR interest",
    "FEMA NRI",
    "RBI NRI",
    "NRI mutual fund",
    "repatriation NRI",
    "NRE NRO account",
]

MACRO_QUERIES = [
    "Nifty 50",
    "Sensex",
    "Indian stock market",
    "gold price India",
    "silver price India",
]

# Shared sentiment keyword lists — single source of truth so pages never
# drift out of sync with each other again.
# NOTE: "up" was removed — it's a common English word that false-matches
# inside unrelated phrases ("Tears Up", "Signs Up", etc.) far more often
# than it correctly signals a price move in a headline.
POSITIVE_WORDS = ["gain", "profit", "rise", "growth", "high", "record",
                   "beat", "strong", "surge", "rally", "jump"]
NEGATIVE_WORDS = ["loss", "fall", "down", "drop", "cut", "weak", "fraud",
                   "probe", "decline", "slash", "risk", "suit"]

# Per-category staleness windows. Stock/macro news goes stale within a day
# or two; NRI/FEMA/tax rule changes stay relevant for weeks. One blanket
# cutoff for everything under- or over-filters depending on category.
MAX_AGE_DAYS_BY_CATEGORY = {
    "holding": 5,
    "macro": 3,
    "nri_tax": 30,
}
DEFAULT_MAX_AGE_DAYS = 10  # fallback if category is unrecognized


def get_sentiment(title: str) -> str:
    t = (title or "").lower()
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in NEGATIVE_WORDS):
        return "red"
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in POSITIVE_WORDS):
        return "green"
    return "neutral"


def _clean_title(title: str, source: str) -> str:
    """Google News RSS titles are usually 'Headline - Source Name'. The
    source is already shown separately in the UI, so a duplicated ' -
    Source' suffix is just clutter — and it can trip sentiment keywords
    that live in the source's own name (e.g. 'NDTV Profit')."""
    title = (title or "").strip()
    source = (source or "").strip()
    if source and title.lower().endswith(f"- {source.lower()}"):
        title = title[: -(len(source) + 2)].strip(" -")
    return title


def _parse_published(entry):
    """Best-effort published datetime. Returns None if unavailable/unparseable."""
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6])
        except Exception:
            pass
    return None


def time_ago(dt):
    """Institutional-feel relative timestamp, e.g. '2h ago', '3d ago'."""
    if dt is None:
        return ""
    delta = datetime.now() - dt
    secs = delta.total_seconds()
    if secs < 0:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    days = int(secs // 86400)
    if days < 7:
        return f"{days}d ago"
    return dt.strftime("%d %b")


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_one(query: str, category: str, limit: int = 4):
    items = []
    max_age_days = MAX_AGE_DAYS_BY_CATEGORY.get(category, DEFAULT_MAX_AGE_DAYS)
    cutoff = datetime.now() - timedelta(days=max_age_days)
    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        for entry in feed.entries:
            raw_title = entry.get("title", "").strip()
            if not raw_title:
                continue
            pub_dt = _parse_published(entry)
            # Drop stale items (category-specific window). Entries with no
            # parseable date are kept but sorted last (unknown, not fresh).
            if pub_dt is not None and pub_dt < cutoff:
                continue
            source = entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else ""
            title = _clean_title(raw_title, source)
            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": entry.get("published", "") or entry.get("updated", ""),
                "published_dt": pub_dt,
                "source": source,
                "query": query,
                "category": category,
            })
            if len(items) >= limit:
                break
    except Exception:
        pass
    return items


def get_portfolio_news(stock_symbols=None, fund_names=None, gold_symbols=None):
    """Holdings + NRI/tax + macro news, deduped, staleness-filtered per
    category, and globally sorted newest-first. Each item is tagged with a
    'category' of 'holding', 'nri_tax', or 'macro' so callers can guarantee
    visibility across categories instead of letting one crowd out another.
    """
    holding_queries = []

    if stock_symbols:
        for s in stock_symbols[:6]:
            if s:
                # Appending "share price" anchors the search to a financial
                # context. Without it, short tickers that are also ordinary
                # words (e.g. ETERNAL, BLS) pull in unrelated pop-culture or
                # government-statistics results that happen to share the word.
                holding_queries.append(f"{str(s).strip()} share price")
    if fund_names:
        for name in fund_names[:3]:
            short = str(name).split(" - ")[0].split(" FUND")[0].strip()
            if short:
                holding_queries.append(short)
    if gold_symbols:
        holding_queries.append("Sovereign Gold Bond")
        holding_queries.append("Gold ETF India")

    all_queries = (
        [(q, "holding") for q in holding_queries]
        + [(q, "nri_tax") for q in NRI_TAX_QUERIES]
        + [(q, "macro") for q in MACRO_QUERIES]
    )
    seen_q = set()
    unique_queries = []
    for q, cat in all_queries:
        qn = q.strip().lower()
        if qn and qn not in seen_q:
            seen_q.add(qn)
            unique_queries.append((q.strip(), cat))

    all_items = []
    seen_titles = set()
    for q, cat in unique_queries:
        for item in _fetch_one(q, cat, limit=3):
            if item["title"] not in seen_titles:
                seen_titles.add(item["title"])
                all_items.append(item)

    # Newest first. Unknown-date items (published_dt is None) sort last.
    all_items.sort(key=lambda x: x["published_dt"] or datetime.min, reverse=True)
    return all_items


def pick_balanced(news_items, total=8, min_nri_tax=2):
    """Select items for a compact summary view without letting holdings
    crowd out NRI/tax news entirely. Reserves `min_nri_tax` slots for
    nri_tax items when available; if none exist, those slots simply go to
    the next most recent items instead (no NRI/tax news being published
    right now is a content gap, not a bug).
    """
    if len(news_items) <= total:
        return news_items

    nri_tax = [i for i in news_items if i["category"] == "nri_tax"]
    others = [i for i in news_items if i["category"] != "nri_tax"]

    reserved = nri_tax[:min_nri_tax]
    remaining_slots = max(0, total - len(reserved))
    rest_pool = others + nri_tax[min_nri_tax:]
    rest_pool.sort(key=lambda x: x["published_dt"] or datetime.min, reverse=True)
    filled = reserved + rest_pool[:remaining_slots]

    filled.sort(key=lambda x: x["published_dt"] or datetime.min, reverse=True)
    return filled
