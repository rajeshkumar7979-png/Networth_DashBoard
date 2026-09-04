import streamlit as st
import pandas as pd

st.title("Deep Health · Decision desk")
st.caption("Decision support for maturing money and allocation choices. Not investment advice.")

st.page_link("pages/1_Command_Center.py", label="← Command Center", icon="📊")
st.markdown("---")

st.subheader("1. Money that needs a decision")

default_amount = float(st.session_state.get("matured_fd_amount", 0) or 0)

col1, col2 = st.columns(2)
with col1:
    decision_amount = st.number_input(
        "Amount available (₹)",
        min_value=0,
        value=int(default_amount) if default_amount > 0 else 0,
        step=50000,
        help="Auto-filled if Command Center detected a matured FD.",
    )
with col2:
    days_to_need = st.selectbox(
        "When do you need this money?",
        ["0–3 months", "3–12 months", "1–3 years", "3+ years / not sure"],
    )

st.markdown("---")
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
st.subheader("3. Rough impact on portfolio weights")

# Defaults: prefer live session values if Command Center stored them; else sensible NRI-ish fallbacks
_def_eq = float(st.session_state.get("cc_equity_pct", 17.0) or 17.0)
_def_liq = float(st.session_state.get("cc_liquid_pct", 18.0) or 18.0)
_def_inr = float(st.session_state.get("cc_inr_fd_pct", 16.0) or 16.0)
_def_fcnr = float(st.session_state.get("cc_fcnr_pct", 42.0) or 42.0)
_def_gold = float(st.session_state.get("cc_gold_pct", 6.0) or 6.0)
_def_nw = float(st.session_state.get("cc_net_worth", 25_200_000) or 25_200_000)

st.write("Enter your current approximate weights (from Command Center). Gold is kept constant in scenarios.")

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    curr_equity = st.number_input("Equity %", 0.0, 100.0, float(round(_def_eq, 1)), 0.5)
with c2:
    curr_liquid = st.number_input("Liquid MF %", 0.0, 100.0, float(round(_def_liq, 1)), 0.5)
with c3:
    curr_inr_fd = st.number_input("INR FD %", 0.0, 100.0, float(round(_def_inr, 1)), 0.5)
with c4:
    curr_fcnr = st.number_input("FCNR %", 0.0, 100.0, float(round(_def_fcnr, 1)), 0.5)
with c5:
    curr_gold = st.number_input("Gold %", 0.0, 100.0, float(round(_def_gold, 1)), 0.5)

total_nw = st.number_input("Current Net Worth (₹)", min_value=1.0, value=float(round(_def_nw, 0)), step=100000.0)

mode = st.radio(
    "What is this amount?",
    [
        "Already inside net worth (reallocation) — e.g. matured FD still counted in NW",
        "New money outside net worth (injection)",
    ],
    index=0,
    help="Matured FDs detected by Command Center are usually still inside NW until you redeploy them.",
)
is_reallocation = mode.startswith("Already inside")

source_bucket = "INR FD"
if is_reallocation:
    source_bucket = st.selectbox(
        "Money is currently sitting in",
        ["INR FD", "Liquid MF", "FCNR", "Equity"],
        index=0,
        help="Reallocation subtracts the amount from this bucket, then adds it to the target.",
    )

weight_sum = curr_equity + curr_liquid + curr_inr_fd + curr_fcnr + curr_gold
if abs(weight_sum - 100.0) > 1.5:
    st.warning(
        f"Your weights sum to {weight_sum:.1f}% (expected ~100%). "
        "Scenarios still run, but % may be off if inputs are incomplete."
    )


def _rupee(pct: float) -> float:
    return pct / 100.0 * total_nw


def _apply_move(eq, liq, inr, fcnr, gold, amount, target: str, source: str | None):
    """
    Move `amount` into `target`.
    If source is set (reallocation), subtract from source first; NW unchanged.
    If source is None (new money), only add; NW grows by amount.
    Targets/sources: Equity | Liquid MF | INR FD | FCNR | Gold
    """
    buckets = {
        "Equity": eq,
        "Liquid MF": liq,
        "INR FD": inr,
        "FCNR": fcnr,
        "Gold": gold,
    }
    if source:
        # Cannot pull more than is in the source bucket
        available = buckets[source]
        take = min(amount, available)
        buckets[source] = available - take
        put = take
        new_nw = total_nw  # reallocation
    else:
        put = amount
        new_nw = total_nw + amount  # injection

    buckets[target] = buckets[target] + put

    def pct(x):
        return round(x / new_nw * 100.0, 1) if new_nw > 0 else 0.0

    return {
        "Equity %": pct(buckets["Equity"]),
        "Liquid %": pct(buckets["Liquid MF"]),
        "INR FD %": pct(buckets["INR FD"]),
        "FCNR %": pct(buckets["FCNR"]),
        "Gold %": pct(buckets["Gold"]),
        "New NW (₹)": int(round(new_nw, 0)),
    }


if decision_amount > 0 and total_nw > 0:
    eq0, liq0, inr0, fcnr0, gold0 = (
        _rupee(curr_equity),
        _rupee(curr_liquid),
        _rupee(curr_inr_fd),
        _rupee(curr_fcnr),
        _rupee(curr_gold),
    )

    if is_reallocation:
        st.write(
            f"**Reallocation of ₹{decision_amount:,.0f} out of {source_bucket}** "
            f"(net worth stays ≈ ₹{total_nw:,.0f}):"
        )
        src = source_bucket
    else:
        st.write(
            f"**Injection of ₹{decision_amount:,.0f} of new money** "
            f"(net worth rises from ₹{total_nw:,.0f}):"
        )
        src = None

    targets = [
        ("All → INR FD", "INR FD"),
        ("All → Liquid MF", "Liquid MF"),
        ("All → Equity", "Equity"),
        ("All → FCNR", "FCNR"),
        ("50% FD + 50% Liquid", None),  # special
    ]

    scenarios = []
    for label, target in targets:
        if target is None:
            # 50/50 FD + Liquid
            half = decision_amount / 2.0
            if 
