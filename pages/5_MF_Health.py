import streamlit as st
import pandas as pd
from lib.mf_health import analyze_fund

st.title("MF Health Check")
st.caption("Light daily metrics + news flags. Holdings/overlap on demand later.")

st.page_link("pages/1_Command_Center.py", label="← Command Center", icon="📊")

st.markdown("---")

# ---- Get MF list from session or manual ----
st.subheader("Your Mutual Funds")

# Try to reuse data if Command Center already ran
mf_list = st.session_state.get("mf_holdings_for_health", [])

if not mf_list:
    st.info(
        "Open **Command Center** once so it can pass your MF list here. "
        "Or enter funds manually below."
    )
    manual = st.text_area(
        "Paste fund names (one per line)",
        height=120,
        placeholder="Parag Parikh Flexi Cap Fund - Direct Plan - Growth\nHDFC Mid-Cap Opportunities Fund - Direct Plan - Growth",
    )
    if st.button("Analyze manual list"):
        names = [n.strip() for n in manual.splitlines() if n.strip()]
        mf_list = [{"Fund Name": n, "Current Value": 0, "Weight %": 0} for n in names]

if not mf_list:
    st.stop()

# ---- Run analysis ----
results = []
progress = st.progress(0)
status = st.empty()

for i, row in enumerate(mf_list):
    name = row.get("Fund Name") or row.get("fund_name") or str(row)
    value = float(row.get("Current Value") or row.get("current_value") or 0)
    weight = float(row.get("Weight %") or row.get("weight_pct") or 0)

    status.write(f"Analyzing {i+1}/{len(mf_list)}: {name[:50]}...")
    res = analyze_fund(name, current_value=value, weight_pct=weight)
    results.append(res)
    progress.progress((i + 1) / len(mf_list))

status.empty()
progress.empty()

# ---- Display ----
st.subheader("Health Overview")

for res in results:
    if res["status"] != "ok":
        st.warning(f"**{res['fund_name']}** — {res.get('message', 'Error')}")
        continue

    m = res["metrics"]
    score = res["health_score"]

    if score >= 70:
        badge = "🟢"
    elif score >= 50:
        badge = "🟡"
    else:
        badge = "🔴"

    with st.expander(f"{badge} {res['fund_name']}  ·  Score {score}/100", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("1Y CAGR", f"{m.get('cagr_1Y')*100:.1f}%" if m.get("cagr_1Y") is not None else "—")
        c2.metric("3Y CAGR", f"{m.get('cagr_3Y')*100:.1f}%" if m.get("cagr_3Y") is not None else "—")
        c3.metric("5Y CAGR", f"{m.get('cagr_5Y')*100:.1f}%" if m.get("cagr_5Y") is not None else "—")
        c4.metric("Max Drawdown", f"{m.get('max_drawdown')*100:.1f}%" if m.get("max_drawdown") is not None else "—")

        st.caption(
            f"Scheme code: {res['scheme_code']} · "
            f"Latest NAV: {m.get('latest_nav', '—')} ({m.get('latest_date', '')}) · "
            f"Your weight: {res['weight_pct']:.1f}%"
        )

        # Placeholder for future news flags
        st.markdown("**News flags:** (coming next — will show manager/strategy alerts here)")

st.markdown("---")
st.info(
    "Holdings & stock overlap will be added as an on-demand button "
    "(only when you click or when news flags a change)."
)
