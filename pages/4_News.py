import streamlit as st
from lib.news import get_portfolio_news, get_sentiment, time_ago

st.title("News · Holdings + NRI / Tax")
st.caption("Full list, sorted newest first. Command Center shows only a short summary.")

st.page_link("pages/1_Command_Center.py", label="← Back to Command Center", icon="📊")

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
    st.info("No recent news found this run.")
    st.stop()

CATEGORY_LABELS = {"holding": "Holding", "nri_tax": "NRI / Tax", "macro": "Market"}

for item in news_items:
    s = get_sentiment(item["title"])
    mark = "🟢" if s == "green" else ("🔴" if s == "red" else "⚪")
    age = time_ago(item.get("published_dt"))
    cat_label = CATEGORY_LABELS.get(item.get("category"), "")

    st.markdown(
        f"""{mark} **[{item['title']}]({item['link']})**  
        <span style="color:#888;font-size:0.8rem">{item.get('source','')} · {age} · {cat_label} · {item.get('query','')}</span>""",
        unsafe_allow_html=True,
    )
    st.markdown("")
