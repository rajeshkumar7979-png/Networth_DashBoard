import streamlit as st
from collections import defaultdict
from lib.mf_health import analyze_fund, get_news_flags, try_fetch_holdings

st.markdown("""
<style>
html, body, [class*="css"] { color: #e8e8e8 !important; }

/* Expander header – always readable */
div[data-testid="stExpander"] details summary {
    background-color: #252536 !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
}
div[data-testid="stExpander"] details summary p,
div[data-testid="stExpander"] details summary span {
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.98rem !important;
}

/* Metrics */
div[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-weight: 700 !important;
}
div[data-testid="stMetricLabel"] {
    color: #c8c8c8 !important;
}

.stCaption, [data-testid="stCaptionContainer"] { color: #b8b8b8 !important; }
.stMarkdown, .stMarkdown p { color: #e0e0e0 !important; }

.flag-item { color: #fbbf24 !important; font-size: 0.9rem; margin-bottom: 3px; }
</style>
""", unsafe_allow_html=True)

st.title("MF Health Check")
st.caption("Light metrics + news + on-demand holdings/overlap")

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
    results.append(analyze_fund(name, value, weight))
    progress.progress((i + 1) / len(mf_list))
progress.empty()

ok_results = [r for r in results if r["status"] == "ok"]
fail_results = [r for r in results if r["status"] != "ok"]

st.subheader(f"Health Overview · {len(ok_results)} funds")

for res in ok_results:
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
            f"Code: {res['scheme_code']} · NAV: {m.get('latest_nav', '—')} ({m.get('latest_date', '')}) · Weight: {res['weight_pct']:.1f}%"
        )

        flags = get_news_flags(res["fund_name"])
        if flags:
            st.markdown("**News & market flags**")
            for f in flags:
                st.markdown(f"<div class='flag-item'>⚠️ {f}</div>", unsafe_allow_html=True)
        else:
            st.caption("No major recent flags.")

if fail_results:
    with st.expander(f"Could not match ({len(fail_results)} funds)", expanded=False):
        for r in fail_results:
            st.write(f"• {r['fund_name']}")

# ---------- Holdings & Overlap (on demand) ----------
st.markdown("---")
st.subheader("Holdings & Stock Overlap")

if st.button("Check Holdings & Overlap (may take 20–40 sec)", type="primary"):
    with st.spinner("Fetching holdings where available..."):
        stock_map = defaultdict(list)  # stock -> list of (fund, weight)
        for res in ok_results:
            holdings = try_fetch_holdings(res["scheme_code"])
            for h in holdings:
                stock_map[h["name"]].append((res["fund_name"][:40], h["weight"]))

        if not stock_map:
            st.warning(
                "No holdings data returned from free source (mfdata.in). "
                "This source is experimental. We can later add monthly AMFI disclosure parsing."
            )
        else:
            # Sort by how many funds hold the stock
            ranked = sorted(stock_map.items(), key=lambda x: len(x[1]), reverse=True)
            st.markdown("**Stocks appearing in multiple funds**")
            rows = []
            for stock, appearances in ranked[:25]:
                funds = ", ".join([f"{f} ({w:.1f}%)" for f, w in appearances])
                rows.append({
                    "Stock": stock,
                    "Funds count": len(appearances),
                    "Appears in": funds,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("Weights are as reported by the fund. This is approximate look-through only.")
else:
    st.caption("Click the button only when you want holdings data (saves API calls).")
