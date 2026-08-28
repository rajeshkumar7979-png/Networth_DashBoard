import streamlit as st
from lib.news import get_portfolio_news

st.title("News · Holdings + NRI / Tax")
st.caption("Full list. Command Center shows only a short summary.")

st.page_link("pages/1_Command_Center.py", label="← Back to Command Center", icon="📊")

# We need the same data the main page uses.
# For now this page works standalone with empty holdings
# (we will connect real symbols later if needed)

stock_syms = st.session_state.get("stock_syms", [])
fund_names = st.session_state.get("fund_names", [])
gold_syms = st.session_state.get("gold_syms", [])

try:
    news_items = get_portfolio_news(
        stock_symbols=stock_syms,
        fund_names=fund_names,
        gold_symbols=gold_syms,
    )
except Exception:
    news_items = []

if not news_items:
    st.info("No news found this run.")
    st.stop()

# Simple sentiment
POSITIVE = ["gain", "profit", "rise", "up", "growth", "high", "record", "beat", "strong", "surge", "rally"]
NEGATIVE = ["loss", "fall", "down", "drop", "cut", "weak", "fraud", "probe", "decline", "slash", "risk"]

def sentiment(title):
    t = title.lower()
    if any(w in t for w in NEGATIVE):
        return "red"
    if any(w in t for w in POSITIVE):
        return "green"
    return "neutral"

for item in news_items:
    s = sentiment(item["title"])
    if s == "green":
        mark = "🟢"
    elif s == "red":
        mark = "🔴"
    else:
        mark = "⚪"

    st.markdown(
        f"""{mark} **[{item['title']}]({item['link']})**  
        <span style="color:#888;font-size:0.8rem">{item.get('source','')} · {item.get('published','')} · {item.get('query','')}</span>""",
        unsafe_allow_html=True,
    )
    st.markdown("")
