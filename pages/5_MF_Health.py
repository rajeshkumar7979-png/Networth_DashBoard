import streamlit as st
import pandas as pd
from lib.mf_health import analyze_fund, get_news_flags

st.markdown("""
<style>
div[data-testid="stExpander"] details summary p {
    color: #e8e8e8 !important;
    font-weight: 600;
}
div[data-testid="stMetricValue"] {
    color: #f0f0f0 !important;
}
div[data-testid="stMetricLabel"] {
    color: #aaaaaa !important;
}
.fund-card {
    background: #1e1e2e;
    border: 1px solid #333;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
.score-good { color: #4ade80; }
.score-ok   { color: #facc15; }
.score-bad  { color: #f87171; }
.flag-item  { color: #fbbf24; font-size: 0.9rem; }
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

# ---- Analyze ----
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

# ---- Summary ----
st.subheader(f"Health Overview  ·  {len(ok_results)} funds")

for res in ok_results:
    m = res["metrics"]
    score = res["health_score"]
    if score >= 70:
        badge = "🟢"
        cls = "score-good"
    elif score >= 50:
        badge = "🟡"
        cls = "score-ok"
    else:
        badge = "🔴"
        cls = "score-bad"

    with st.expander(f"{badge}  {res['fund_name']}   ·   Score {score}/100", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("1Y CAGR", f"{m['cagr_1Y']*100:.1f}%" if m.get("cagr_1Y") is not None else "—")
        c2.metric("3Y CAGR", f"{m['cagr_3Y']*100:.1f}%" if m.get("cagr_3Y") is not None else "—")
        c3.metric("5Y CAGR", f"{m['cagr_5Y']*100:.1f}%" if m.get("cagr_5Y") is not None else "—")
        c4.metric("Max DD", f"{m['max_drawdown']*100:.1f}%" if m.get("max_drawdown") is not None else "—")

        st.caption(
            f"Code: {res['scheme_code']}  ·  NAV: {m.get('latest_nav', '—')} ({m.get('latest_date', '')})  ·  Weight: {res['weight_pct']:.1f}%"
        )

        # News flags
        flags = get_news_flags(res["fund_name"])
        if flags:
            st.markdown("**News flags**")
            for f in flags:
                st.markdown(f"<div class='flag-item'>⚠️ {f}</div>", unsafe_allow_html=True)
        else:
            st.caption("No major manager/strategy news found recently.")

# ---- Failed ones (collapsed) ----
if fail_results:
    with st.expander(f"Could not match ({len(fail_results)} funds)", expanded=False):
        for r in fail_results:
            st.write(f"• {r['fund_name']}")

st.markdown("---")
st.info("Holdings & stock overlap will be added next as an on-demand button.")
