import streamlit as st
from lib.mf_health import analyze_fund, get_news_flags

st.markdown("""
<style>
/* Force readable text everywhere on this page */
html, body, [class*="css"] {
    color: #e8e8e8 !important;
}

/* Expander title */
div[data-testid="stExpander"] details summary p,
div[data-testid="stExpander"] details summary span {
    color: #f1f1f1 !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
}

/* Metric numbers */
div[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-weight: 700 !important;
}

/* Metric labels */
div[data-testid="stMetricLabel"] {
    color: #c0c0c0 !important;
}

/* Caption text */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #b0b0b0 !important;
}

/* General markdown */
.stMarkdown, .stMarkdown p {
    color: #e0e0e0 !important;
}

/* Score colors */
.score-good { color: #4ade80 !important; }
.score-ok   { color: #facc15 !important; }
.score-bad  { color: #f87171 !important; }

/* News flag */
.flag-item {
    color: #fbbf24 !important;
    font-size: 0.9rem;
    margin-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)

st.title("MF Health Check")
st.caption("Light metrics + news flags. Holdings on demand.")

st.page_link("pages/1_Command_Center.py", label="← Command Center", icon="📊")
st.markdown("---")

mf_list = st.session_state.get("mf_holdings_for_health", [])

if not mf_list:
    st.info("Open **Command Center** once so your funds are loaded here.")
    st.stop()

# Analyze
results = []
progress = st.progress(0)
for i, row in enumerate(mf_list):
    name = row.get("Fund Name") or str(row)
    value = float(row.get("Current Value") or 0)
    weight = float(row.get("Weight %") or 0)
    res = analyze_fund(name, current_value=value, weight_pct=weight)
    results.append(res)
    progress.progress((i + 1) / len(mf_list))
progress.empty()

ok_results = [r for r in results if r["status"] == "ok"]
fail_results = [r for r in results if r["status"] != "ok"]

st.subheader(f"Health Overview · {len(ok_results)} funds")

for res in ok_results:
    m = res["metrics"]
    score = res["health_score"]

    if score >= 70:
        badge = "🟢"
    elif score >= 50:
        badge = "🟡"
    else:
        badge = "🔴"

    title = f"{badge}  {res['fund_name']}   ·   Score {score}/100"

    with st.expander(title, expanded=False):
        c1, c2, c3, c4 = st.columns(4)

        def fmt_pct(val):
            return f"{val*100:.1f}%" if val is not None else "—"

        c1.metric("1Y CAGR", fmt_pct(m.get("cagr_1Y")))
        c2.metric("3Y CAGR", fmt_pct(m.get("cagr_3Y")))
        c3.metric("5Y CAGR", fmt_pct(m.get("cagr_5Y")))
        c4.metric("Max DD", fmt_pct(m.get("max_drawdown")))

        st.caption(
            f"Code: {res['scheme_code']}  ·  "
            f"NAV: {m.get('latest_nav', '—')} ({m.get('latest_date', '')})  ·  "
            f"Weight: {res['weight_pct']:.1f}%"
        )

        flags = get_news_flags(res["fund_name"])
        if flags:
            st.markdown("**News flags**")
            for f in flags:
                st.markdown(f"<div class='flag-item'>⚠️ {f}</div>", unsafe_allow_html=True)
        else:
            st.caption("No major manager/strategy news found recently.")

if fail_results:
    with st.expander(f"Could not match ({len(fail_results)} funds)", expanded=False):
        for r in fail_results:
            st.write(f"• {r['fund_name']}")

st.markdown("---")
st.info("Next: on-demand Holdings & stock overlap button.")
