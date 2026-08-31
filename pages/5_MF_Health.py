import streamlit as st
import pandas as pd
from collections import defaultdict
from lib.mf_health import analyze_fund, get_news_flags, get_holdings_for_funds

st.markdown("""
<style>
html, body, [class*="css"] { color: #e8e8e8 !important; }
div[data-testid="stExpander"] details summary {
    background-color: #252536 !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
}
div[data-testid="stExpander"] details summary p,
div[data-testid="stExpander"] details summary span {
    color: #ffffff !important;
    font-weight: 600 !important;
}
div[data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 700 !important; }
div[data-testid="stMetricLabel"] { color: #c8c8c8 !important; }
.stCaption, [data-testid="stCaptionContainer"] { color: #b8b8b8 !important; }
.flag-item { color: #fbbf24 !important; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

st.title("MF Health Check")
st.caption("Codes from Command Center AMFI map · News flags · Monthly-cached overlap")

st.page_link("pages/1_Command_Center.py", label="← Command Center", icon="📊")
st.markdown("---")

mf_list = st.session_state.get("mf_holdings_for_health", [])
if not mf_list:
    st.info("Open **Command Center** once so your funds + scheme codes are loaded here.")
    st.stop()

raw_results = []
progress = st.progress(0)
for i, row in enumerate(mf_list):
    name = row.get("Fund Name") or str(row)
    value = float(row.get("Current Value") or 0)
    weight = float(row.get("Weight %") or 0)
    scheme_code = row.get("Scheme Code")
    raw_results.append(analyze_fund(name, value, weight, scheme_code))
    progress.progress((i + 1) / len(mf_list))
progress.empty()

by_code = {}
no_code = []
for r in raw_results:
    code = r.get("scheme_code")
    if not code:
        no_code.append(r)
        continue
    prev = by_code.get(code)
    if prev is None or r.get("weight_pct", 0) > prev.get("weight_pct", 0):
        by_code[code] = r

ok_results = [r for r in by_code.values() if r["status"] == "ok"]
no_metrics = [r for r in by_code.values() if r["status"] == "no_metrics"]
fail_results = no_code + [r for r in by_code.values() if r["status"] == "not_found"]

st.subheader(f"Health Overview · {len(ok_results)} unique funds")

for res in sorted(ok_results, key=lambda x: -x.get("weight_pct", 0)):
    m = res["metrics"]
    score = res["health_score"]
    badge = "🟢" if score >= 70 else ("🟡" if score >= 50 else "🔴")
    with st.expander(f"{badge}  {res['fund_name']}   ·   Score {score}/100", expanded=False):
        c1, c2, c3, c4 = st.columns(4)

        def fmt(v):
            return f"{v*100:.1f}%" if v is not None else "—"

        c1.metric("1Y CAGR", fmt(m.get("cagr_1Y")))
        c2.metric("3Y CAGR", fmt(m.get("cagr_3Y")))
        c3.metric("5Y CAGR", fmt(m.get("cagr_5Y")))
        c4.metric("Max DD", fmt(m.get("max_drawdown")))
        st.caption(
            f"Code: {res['scheme_code']} · NAV: {m.get('latest_nav', '—')} "
            f"({m.get('latest_date', '')}) · Weight: {res['weight_pct']:.1f}%"
        )
        flags = get_news_flags(res["fund_name"])
        if flags:
            st.markdown("**News & market flags**")
            for f in flags:
                st.markdown(f"<div class='flag-item'>⚠️ {f}</div>", unsafe_allow_html=True)
        else:
            st.caption("No major recent flags.")

if no_metrics:
    with st.expander(f"Code found but no returns ({len(no_metrics)})", expanded=False):
        for r in no_metrics:
            st.write(f"• {r['fund_name']} (code {r.get('scheme_code')})")

if fail_results:
    with st.expander(f"Could not match ({len(fail_results)})", expanded=False):
        for r in fail_results:
            st.write(f"• {r['fund_name']}")

st.markdown("---")
st.subheader("Holdings & Stock Overlap")
st.caption(
    "Cached monthly — SEBI portfolio disclosures do not change daily. "
    "Only re-fetches once a month per fund (or when you force refresh)."
)

force = st.button("Force refresh now (hits mfdata.in live — may be slow)")

codes = [res["scheme_code"] for res in ok_results]
holdings_by_code, cache = get_holdings_for_funds(codes, force_refresh=force)

if not holdings_by_code:
    st.warning(
        "No cached holdings yet and mfdata.in did not respond. "
        "Try Force refresh again later, or check overlapiq.in / AMC factsheet."
    )
else:
    stock_map = defaultdict(list)
    for res in ok_results:
        for h in holdings_by_code.get(res["scheme_code"], []):
            stock_map[h["name"]].append((res["fund_name"][:36], h["weight"]))

    ages = [cache[str(c)]["fetched_at"][:10] for c in codes if str(c) in cache]
    if ages:
        st.caption(f"Holdings cached as of {min(ages)} – {max(ages)}.")

    if stock_map:
        ranked = sorted(stock_map.items(), key=lambda x: len(x[1]), reverse=True)
        rows = [
            {
                "Stock": s,
                "Funds": len(a),
                "Details": ", ".join(f"{f} ({w:.1f}%)" for f, w in a),
            }
            for s, a in ranked[:30]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Cache exists but no stock rows parsed yet. Try Force refresh.")
