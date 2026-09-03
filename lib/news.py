import feedparser
import streamlit as st
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Query sets — kept separate on purpose:
#   NRI_TAX_QUERIES   -> genuinely NRI/FEMA/tax-specific, the differentiator
#                        content for this app. Never crowded out by holdings.
#   MACRO_QUERIES     -> broad market pulse (Nifty/Sensex/gold/silver). Useful
#                        context, but not holding-specific and not NRI-specific.
# Mixing these previously meant NRI/tax news could be silently pushed off the
# Command Center summary once enough holdings queries were inserted first.
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
POSITIVE_WORDS = ["gain", "profit", "rise", "up", "growth", "high", "record",
                   "beat", "strong", "surge", "rally", "jump"]
NEGATIVE_WORDS = ["loss", "fall", "down", "drop", "cut", "weak", "fraud",
                   "probe", "decline", "slash", "risk", "suit"]

# Default: don't show news older than this. Google News RSS can and does
# return week(s)-old cached items for low-volume queries (e.g. a small fund
# name); without a cutoff these persist indefinitely.
DEFAULT_MAX_AGE_DAYS = 10


def get_sentiment(title: str) -> str:
    t = (title or "").lower()
    if any(w in t for w in NEGATIVE_WORDS):
        return "red"
    if any(w in t for w in POSITIVE_WORDS):
        return "green"
    return "neutral"


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
def _fetch_one(query: str, category: str, limit: int = 4, max_age_days: int = DEFAULT_MAX_AGE_DAYS):
    items = []
    cutoff = datetime.now() - timedelta(days=max_age_days)
    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            if not title:
                continue
            pub_dt = _parse_published(entry)
            # Drop stale items. Entries with no parseable date are kept but
            # sorted last (treated as unknown-age, not assumed-fresh).
            if pub_dt is not None and pub_dt < cutoff:
                continue
            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": entry.get("published", "") or entry.get("updated", ""),
                "published_dt": pub_dt,
                "source": entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
                "query": query,
                "category": category,
            })
            if len(items) >= limit:
                break
    except Exception:
        pass
    return items


def get_portfolio_news(stock_symbols=None, fund_names=None, gold_symbols=None,
                        max_age_days: int = DEFAULT_MAX_AGE_DAYS):
    """Holdings + NRI/tax + macro news, deduped, staleness-filtered, and
    globally sorted newest-first. Each item is tagged with a 'category' of
    'holding', 'nri_tax', or 'macro' so callers can guarantee visibility
    across categories instead of letting one crowd out another.
    """
    holding_queries = []

    if stock_symbols:
        holding_queries.extend([str(s).strip() for s in stock_symbols[:6] if s])
    if fund_names:
        for name in fund_names[:3]:
            short = str(name).split(" - ")[0].split(" FUND")[0].strip()
            if short:
                holding_queries.append(short)
    if gold_symbols:
        holding_queries.append("Sovereign Gold Bond")
        holding_queries.append("Gold ETF India")

    # (query, category) pairs, deduplicated by normalized query text
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
        for item in _fetch_one(q, cat, limit=3, max_age_days=max_age_days):
            if item["title"] not in seen_titles:
                seen_titles.add(item["title"])
                all_items.append(item)

    # Newest first. Unknown-date items (published_dt is None) sort last.
    all_items.sort(key=lambda x: x["published_dt"] or datetime.min, reverse=True)
    return all_items


def pick_balanced(news_items, total=8, min_nri_tax=2):
    """Select items for a compact summary view without letting holdings
    crowd out NRI/tax news entirely. Reserves `min_nri_tax` slots for
    nri_tax items (if available) before filling the rest by recency.
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
