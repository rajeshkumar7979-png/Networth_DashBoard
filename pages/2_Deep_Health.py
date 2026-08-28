import streamlit as st
import pandas as pd

st.title("Deep Health · Decision desk")
st.caption("Decision support for maturing money and allocation choices. Not investment advice.")

st.markdown("---")

# ----- Quick decision inputs -----
st.subheader("1. Money that needs a decision")

col1, col2 = st.columns(2)
with col1:
    decision_amount = st.number_input(
        "Amount available (₹)",
        min_value=0,
        value=0,
        step=50000,
        help="Usually a maturing FD or surplus cash",
    )
with col2:
    days_to_need = st.selectbox(
        "When do you need this money?",
        ["0–3 months", "3–12 months", "1–3 years", "3+ years / not sure"],
    )

st.markdown("---")

# ----- Simple recommendation logic -----
st.subheader("2. Suggested direction")

if decision_amount <= 0:
    st.info("Enter an amount above to see suggestions.")
else:
    if days_to_need == "0–3 months":
        st.success("**Prefer Liquid / short FD**")
        st.write("- Keep in Liquid Mutual Fund or short-term FD")
        st.write("- Do not put this money into equity right now")
    elif days_to_need == "3–12 months":
        st.warning("**Prefer short FD + some Liquid**")
        st.write("- Majority in FD maturing near your need date")
        st.write("- Small portion can stay in Liquid fund")
    elif days_to_need == "1–3 years":
        st.info("**Can consider mix**")
        st.write("- Part in FD / debt")
        st.write("- Part can go to equity or hybrid only if you can tolerate ups and downs")
    else:
        st.info("**Longer horizon – equity can be considered**")
        st.write("- Only if this money is truly not needed for 3+ years")
        st.write("- Match with your overall equity target")

st.markdown("---")

# ----- Weight impact calculator -----
st.subheader("3. Rough impact on portfolio weights")

st.write("Enter your current approximate percentages (from Command Center):")

c1, c2, c3, c4 = st.columns(4)
with c1:
    curr_equity = st.number_input("Current Equity %", 0.0, 100.0, 17.0, 0.5)
with c2:
    curr_liquid = st.number_input("Current Liquid %", 0.0, 100.0, 9.0, 0.5)
with c3:
    curr_inr_fd = st.number_input("Current INR FD %", 0.0, 100.0, 26.0, 0.5)
with c4:
    curr_fcnr = st.number_input("Current FCNR %", 0.0, 100.0, 42.0, 0.5)

total_nw = st.number_input("Current Net Worth (₹)", min_value=1, value=25700000, step=100000)

if decision_amount > 0 and total_nw > 0:
    st.write("**If you put the full amount into one bucket:**")

    scenarios = []
    for name, eq_add, liq_add, fd_add in [
        ("All → INR FD", 0, 0, decision_amount),
        ("All → Liquid MF", 0, decision_amount, 0),
        ("All → Equity", decision_amount, 0, 0),
        ("50% FD + 50% Liquid", 0, decision_amount/2, decision_amount/2),
    ]:
        new_eq = curr_equity/100 * total_nw + eq_add
        new_liq = curr_liquid/100 * total_nw + liq_add
        new_fd = curr_inr_fd/100 * total_nw + fd_add
        scenarios.append({
            "Scenario": name,
            "Equity %": round(new_eq / total_nw * 100, 1),
            "Liquid %": round(new_liq / total_nw * 100, 1),
            "INR FD %": round(new_fd / total_nw * 100, 1),
        })

    st.dataframe(pd.DataFrame(scenarios), use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("This is only a decision helper. Final choice depends on your cash needs, risk comfort and tax situation.")
