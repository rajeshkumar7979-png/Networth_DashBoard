import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from collections import defaultdict
from datetime import datetime
from lib.mf_health import analyze_fund, get_news_flags, get_holdings_for_funds

st.set_page_config(page_title="MF Health Check", page_icon="🛡️", layout="wide")

# ==================================================
# INSTITUTIONAL DARK THEME
# ==================================================
st.markdown("""
<style>
.stApp { background: #0a0e17; }
p, span, label, .stMarkdown, div[data-testid="stMarkdownContainer"] { color: #c2c9d6 !important; }
.block-container { padding-top: 1.4rem; max-width: 1500px; }

.mfh-card {
    background: linear-gradient(155deg, #12182a 0%, #0e1420 100%);
    border: 1px solid #1c2333; border-radius: 14px; padding: 16px 18px;
}
.mfh-kpi-label { font-size: 0.68rem; font-weight: 700; color: #6b7688;
                  text-transform: uppercase; letter-spacing: 0.06em; }
.mfh-kpi-val { font-size: 1.55rem; font-weight: 800; color: #f8fafc; margin: 4px 0 2px 0; }
.mfh-kpi-sub { font-size: 0.72rem; color: #6b7688; }
.mfh-badge { display:inline-block; padding:2px 9px; border-radius:999px; font-size:0.68rem; font-weight:700; }
.badge-low    { background: rgba(34,197,94,0.14);  color:#4ade80; }
.badge-mod    { background: rgba(245,158,11,0.14); color:#fbbf24; }
.badge-high   { background: rgba(239,68,68,0.14);  color:#f87171; }
.badge-vhigh  { background: rgba(239,68,68,0.22);  color:#fca5a5; }

.score-circle {
    display:inline-flex; align-items:center; justify-content:center;
    width:38px; height:38px; border-radius:50%; font-weight:800; font-size:0.82rem;
    border: 3px solid;
}
.sc-excellent { border-color:#22c55e; color:#4ade80; }
.sc-good      { border-color:#eab308; color:#fbbf24; }
.sc-average   { border-color:#f97316; color:#fb923c; }
.sc-poor      { border-color:#ef4444; color:#f87171; }

.fund-row { border-bottom: 1px solid #1c2333; padding: 10px 4px; }
.fund-name { color:#f1f5f9 !important; font-weight:600; font-size:0.86rem; }
.fund-amc  { color:#6b7688 !important; font-size:0.72rem; }
.cat-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#3b82f6; margin-right:6px; }
.section-header { font-size:0.78rem; font-weight:700; color:#8b95a8; text-transform:uppercase;
                   letter-spacing:0.07em; margin: 18px 0 8px 0; }
</style>
""", unsafe_allow_html=True)

# ==================================================
# LOAD FUNDS FROM COMMAND CENTER (unchanged data path)
# ==================================================
st.page_link("pages/1_Command_Center.py", label="← Command Center", icon="📊")

mf_list = st.session_state.get("mf_holdings_for_health", [])
if not mf_list:
    st.info("Open **Command Center** once so your funds + scheme codes are loaded here.")
    st.stop()

raw_results = []
for row in mf_list:
    name = row.get("Fund Name") or str(row)
    value = float(row.get("Current Value") or 0)
    weight = float(row.get("Weight %") or 0)
    scheme_code = row.get("Scheme Code")
    raw_results.append(analyze_fund(
        name, value, weight, scheme_code,
        cagr_1y=row.get("1Y %"), cagr_3y=row.get("3Y %"), cagr_5y=row.get("5Y %"),
        latest_nav=row.get("Current NAV"),
    ))

by_code = {}
for r in raw_results:
    code = r.get("scheme_code")
    if not code:
        continue
    prev = by_code.get(code)
    if prev is None or r.get("weight_pct", 0) > prev.get("weight_pct", 0):
        by_code[code] = r

ok_results = [r for r in by_code.values() if r["status"] == "ok"]
if not ok_results:
    st.warning("No funds with usable data yet.")
    st.stop()

total_value = sum(r["current_value"] for r in ok_results)

# ==================================================
# CATEGORY (reuse Command Center's category text via fund name heuristics
# already stored — fall back to generic label; never invented AUM/expense data)
# ==================================================
import re
CATEGORY_RULES = [
    ("Liquid", r"liquid"), ("Small Cap", r"small\s*cap"), ("Mid Cap", r"mid\s*cap"),
    ("Large Cap", r"large\s*cap|bluechip"), ("Flexi Cap", r"flexi\s*cap|multi\s*cap"),
    ("Index", r"index|next\s*50|nifty\s*50\b"), ("Hybrid", r"hybrid|balanced"),
    ("Contra/Value", r"contra|value\s*discovery"),
    ("Thematic", r"infra|defence|bharat\s*22|fof|reform"),
]
def infer_category(name):
    n = (name or "").lower()
    for label, pat in CATEGORY_RULES:
        if re.search(pat, n):
            return label
    return "Other Equity"

def infer_amc(name):
    n = (name or "").strip()
    for amc in ["HDFC", "ICICI Prudential", "ICICI", "SBI", "DSP", "Nippon India", "Mirae Asset",
                "Invesco India", "Invesco", "Quant", "UTI", "Kotak", "Parag Parikh", "Axis",
                "ITI", "Edelweiss"]:
        if n.upper().startswith(amc.upper()):
            return amc
    return n.split()[0] if n else "—"

# ==================================================
# PILLAR SCORING — every pillar traces to a real number; nothing fabricated.
# Cost is explicitly N/A (no free expense-ratio source found).
# ==================================================
def consistency_score(m):
    vals = [m.get("cagr_1Y"), m.get("cagr_3Y"), m.get("cagr_5Y")]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return 10.0  # neutral — not enough history to judge either way
    spread = (max(vals) - min(vals))
    return float(np.clip(20 - spread * 40, 0, 20))

def performance_score(m):
    c3 = m.get("cagr_3Y")
    if c3 is None:
        return 12.5
    if c3 > 0.18: return 25.0
    if c3 > 0.12: return 20.0
    if c3 > 0.08: return 14.0
    if c3 > 0.04: return 8.0
    return 3.0

def concentration_score(weight_pct):
    # Smaller position in YOUR portfolio = lower single-fund concentration risk
    if weight_pct <= 5: return 15.0
    if weight_pct <= 15: return 11.0
    if weight_pct <= 25: return 6.0
    return 2.0

def risk_adjusted_score(m):
    c3, dd = m.get("cagr_3Y"), m.get("max_drawdown")
    if c3 is None or dd is None or dd == 0:
        return 5.0
    calmar = c3 / abs(dd)
    return float(np.clip(calmar * 8, 0, 10))

def overlap_pillar_score(overlap_pct):
    if overlap_pct is None:
        return None  # unknown — excluded from total, not guessed
    return float(np.clip(20 - overlap_pct * 0.4, 0, 20))

# ==================================================
# HOLDINGS OVERLAP (best-effort; honest empty state if unavailable)
# ==================================================
codes = [r["scheme_code"] for r in ok_results]
holdings_by_code, cache = get_holdings_for_funds(codes, force_refresh=False)

def _is_equity_holding(h):
    """Only real equity positions belong in the stock-overlap analysis."""
    typ = str(h.get("instrument_type") or "").strip().lower()
    if typ:
        return typ in {"equity", "stock", "listed_equity", "equity_share"}
    # Conservative fallback when an old cache has no instrument_type.
    name = str(h.get("name") or "").lower()
    blocked = ("bond", "debenture", "certificate of deposit", "treasury",
               "t-bill", "g-sec", "government security", "commercial paper",
               "money market", "cash", "liquid fund", "etf", "fund of fund")
    return not any(x in name for x in blocked)

def _holding_key(h):
    isin = str(h.get("isin") or "").strip().upper()
    if isin and isin != "-":
        return "ISIN:" + isin
    name = re.sub(r"[^A-Z0-9]", "", str(h.get("name") or "").upper())
    return "NAME:" + name if name else None

# security key -> [(fund_name, weight_in_fund, fund_value, display_name)]
stock_exposure = defaultdict(list)
for r in ok_results:
    code = r["scheme_code"]
    for h in holdings_by_code.get(code, []):
        if not _is_equity_holding(h):
            continue
        key = _holding_key(h)
        weight = h.get("weight")
        if not key or not isinstance(weight, (int, float)) or weight <= 0:
            continue
        stock_exposure[key].append((
            r["fund_name"], float(weight), float(r["current_value"]),
            str(h.get("name") or "—")
        ))

overlap_available = any(len({x[0] for x in apps}) > 1 for apps in stock_exposure.values())

# Per-fund overlap = percentage of that fund's disclosed portfolio invested in
# stocks that are also held by at least one other fund in this portfolio.
per_fund_overlap_pct = {}
for r in ok_results:
    code = r["scheme_code"]
    hlist = holdings_by_code.get(code, [])
    if not hlist:
        per_fund_overlap_pct[code] = None
        continue
    overlapped_keys = {k for k, apps in stock_exposure.items()
                       if len({x[0] for x in apps}) > 1}
    overlap_weight = 0.0
    seen_keys = set()
    for h in hlist:
        if not _is_equity_holding(h):
            continue
        key = _holding_key(h)
        weight = h.get("weight")
        if key in overlapped_keys and key not in seen_keys and isinstance(weight, (int, float)):
            overlap_weight += float(weight)
            seen_keys.add(key)
    per_fund_overlap_pct[code] = overlap_weight

# Portfolio overlap is based on YOUR actual MF allocation, not the average of fund percentages.
# This prevents a small liquid fund and a large equity fund from having equal influence.
overlap_user_value = 0.0
if overlap_available and total_value > 0:
    for key, apps in stock_exposure.items():
        if len({x[0] for x in apps}) < 2:
            continue
        for fund_name, weight, fund_value, _display_name in apps:
            overlap_user_value += fund_value * (weight / 100.0)
    portfolio_overlap_pct = float(np.clip(overlap_user_value / total_value * 100.0, 0, 100))
else:
    portfolio_overlap_pct = None

def overlap_badge(pct):
    if pct is None:
        return "—", ""
    if pct < 10: return "Low", "badge-low"
    if pct < 30: return "Moderate", "badge-mod"
    if pct < 45: return "High", "badge-high"
    return "Very High", "badge-vhigh"

# ==================================================
# ASSEMBLE PER-FUND SCORES
# ==================================================
rows = []
for r in ok_results:
    m = r["metrics"]
    code = r["scheme_code"]
    ov_pct = per_fund_overlap_pct.get(code)
    perf = performance_score(m)
    cons = consistency_score(m)
    conc = concentration_score(r["weight_pct"])
    risk = risk_adjusted_score(m)
    ov_score = overlap_pillar_score(ov_pct)

    parts = [perf, cons, conc, risk] + ([ov_score] if ov_score is not None else [])
    max_parts = [25, 20, 15, 10] + ([20] if ov_score is not None else [])
    total_100 = sum(parts) / sum(max_parts) * 100

    label, cls = overlap_badge(ov_pct)
    rows.append({
        "Fund": r["fund_name"], "AMC": infer_amc(r["fund_name"]),
        "Category": infer_category(r["fund_name"]),
        "1Y": m.get("cagr_1Y"), "3Y": m.get("cagr_3Y"), "5Y": m.get("cagr_5Y"),
        "Weight %": r["weight_pct"], "Value": r["current_value"],
        "Score": round(total_100), "OverlapPct": ov_pct,
        "OverlapLabel": label, "OverlapCls": cls,
        "_perf": perf, "_cons": cons, "_conc": conc, "_risk": risk, "_ov": ov_score,
    })
df = pd.DataFrame(rows).sort_values("Weight %", ascending=False)

overall_health = round(df["Score"].mean())
top5_weight = df.nlargest(5, "Weight %")["Weight %"].sum()

def score_bucket(s):
    if s >= 80: return "Excellent", "sc-excellent"
    if s >= 60: return "Good", "sc-good"
    if s >= 40: return "Average", "sc-average"
    return "Poor", "sc-poor"

def conc_bucket(top5):
    if top5 < 35: return "Low", "#4ade80"
    if top5 < 55: return "Moderate", "#fbbf24"
    return "High", "#f87171"

conc_label, conc_color = conc_bucket(top5_weight)

# ==================================================
# HEADER + KPI ROW
# ==================================================
c_title, c_export = st.columns([5, 1])
with c_title:
    st.markdown("## 🛡️ MF Health Check")
    st.caption("Mutual fund portfolio quality, performance, overlap and concentration")
with c_export:
    st.download_button("⬇ Export", df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(index=False),
                        "mf_health.csv", "text/csv", use_container_width=True)

st.caption(f"Data as of {datetime.now().strftime('%d %b %Y')} · Based on {len(df)} unique funds")
st.markdown("---")

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(f"""<div class="mfh-card"><div class="mfh-kpi-label">MF Portfolio Value</div>
    <div class="mfh-kpi-val">₹{total_value/1e7:.2f} Cr</div>
    <div class="mfh-kpi-sub">of total net worth</div></div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="mfh-card"><div class="mfh-kpi-label">No. of Funds</div>
    <div class="mfh-kpi-val">{len(df)}</div>
    <div class="mfh-kpi-sub">{df['AMC'].nunique()} fund families</div></div>""", unsafe_allow_html=True)
with k3:
    b_label, _ = score_bucket(overall_health)
    st.markdown(f"""<div class="mfh-card" style="text-align:center">
    <div class="mfh-kpi-label">MF Health Score</div>
    <div class="mfh-kpi-val" style="color:#4ade80 !important">{overall_health}<span style="font-size:0.9rem;color:#6b7688">/100</span></div>
    <div class="mfh-kpi-sub" style="color:#4ade80 !important">{b_label}</div></div>""", unsafe_allow_html=True)
with k4:
    ov_txt = f"{portfolio_overlap_pct:.0f}%" if portfolio_overlap_pct is not None else "N/A"
    ov_lbl, ov_cls = overlap_badge(portfolio_overlap_pct)
    st.markdown(f"""<div class="mfh-card"><div class="mfh-kpi-label">Portfolio Overlap</div>
    <div class="mfh-kpi-val">{ov_txt}</div>
    <span class="mfh-badge {ov_cls}">{ov_lbl}</span></div>""", unsafe_allow_html=True)
with k5:
    st.markdown(f"""<div class="mfh-card"><div class="mfh-kpi-label">Concentration Risk</div>
    <div class="mfh-kpi-val" style="color:{conc_color} !important">{conc_label}</div>
    <div class="mfh-kpi-sub">Top 5 funds: {top5_weight:.1f}%</div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ==================================================
# BREAKDOWN RADAR + OVERLAP DONUT + TOP OVERLAPPED STOCKS
# ==================================================
c1, c2, c3 = st.columns([1.1, 0.9, 1.3])

with c1:
    st.markdown('<div class="mfh-card">', unsafe_allow_html=True)
    st.markdown("**MF Portfolio Health Breakdown**")
    pillars = ["Performance\n(25)", "Consistency\n(20)", "Concentration\n(15)", "Risk Adjusted\n(10)"]
    vals = [df["_perf"].mean(), df["_cons"].mean(), df["_conc"].mean(), df["_risk"].mean()]
    if df["_ov"].notna().any():
        pillars.append("Overlap\n(20)")
        vals.append(df["_ov"].mean())
    fig = go.Figure(go.Scatterpolar(r=vals + [vals[0]], theta=pillars + [pillars[0]],
                                     fill="toself", line_color="#22c55e", fillcolor="rgba(34,197,94,0.18)"))
    fig.update_layout(
        polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, showticklabels=False, gridcolor="#1c2333"),
                   angularaxis=dict(gridcolor="#1c2333", color="#8b95a8")),
        showlegend=False, height=280, margin=dict(t=20, b=20, l=40, r=40),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if not df["_ov"].notna().any():
        st.caption("Overlap pillar excluded — holdings data unavailable this run.")
    st.caption("Cost pillar not shown — no free source for per-fund expense ratio.")
    st.markdown("</div>", unsafe_allow_html=True)

with c2:
    st.markdown('<div class="mfh-card">', unsafe_allow_html=True)
    st.markdown("**Portfolio Overlap**")
    if portfolio_overlap_pct is not None:
        fig2 = go.Figure(go.Pie(
            values=[portfolio_overlap_pct, 100 - portfolio_overlap_pct],
            labels=["Overlapped exposure", "Unique exposure"], hole=0.68,
            marker_colors=["#eab308", "#22c55e"], textinfo="none",
        ))
        fig2.update_layout(
            height=230, showlegend=True, legend=dict(orientation="h", y=-0.15, font=dict(size=10, color="#c2c9d6")),
            margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(text=f"{portfolio_overlap_pct:.0f}%<br>Overlap", x=0.5, y=0.5,
                               font_size=15, showarrow=False, font_color="#f8fafc")],
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No holdings data cached yet — click 'Refresh holdings' below.")
    st.markdown("</div>", unsafe_allow_html=True)

with c3:
    st.markdown('<div class="mfh-card">', unsafe_allow_html=True)
    st.markdown("**Top Overlapped Stocks (Equity Only)**")
    if overlap_available:
        rows2 = []
        for key, apps in stock_exposure.items():
            fund_count = len({x[0] for x in apps})
            if fund_count < 2:
                continue
            total_exp = sum(fv * (w / 100.0) for _, w, fv, _ in apps)
            display_name = max(apps, key=lambda x: x[1])[3]
            rows2.append({"Stock": display_name, "In Funds": fund_count,
                          "Total Exposure": total_exp, "% of MF Portfolio": total_exp / total_value * 100})
        if rows2:
            top_df = pd.DataFrame(rows2).sort_values(
                ["In Funds", "Total Exposure"], ascending=[False, False]
            ).head(5)
            for _, rr in top_df.iterrows():
                st.markdown(
                    f"<div class='fund-row' style='display:flex;justify-content:space-between'>"
                    f"<span class='fund-name'>{rr['Stock']}</span>"
                    f"<span>{rr['In Funds']} funds · ₹{rr['Total Exposure']/1e5:.1f}L · {rr['% of MF Portfolio']:.1f}%</span>"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.caption("No stock appears in more than one fund yet.")
    else:
        st.caption("Holdings data unavailable — cache is empty and mfdata.in hasn't returned data. "
                    "As a manual check meanwhile, try overlapiq.in with your fund list.")
    force = st.button("🔄 Refresh holdings now (may be slow)", use_container_width=True)
    if force:
        get_holdings_for_funds(codes, force_refresh=True)
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ==================================================
# SEARCHABLE / FILTERABLE FUND TABLE
# ==================================================
st.markdown('<div class="section-header">Fund Details</div>', unsafe_allow_html=True)

fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
with fc1:
    search = st.text_input("🔍 Search fund / AMC / Category", "", label_visibility="collapsed",
                            placeholder="Search fund / AMC / Category")
with fc2:
    cat_filter = st.selectbox("Category", ["All Categories"] + sorted(df["Category"].unique().tolist()))
with fc3:
    amc_filter = st.selectbox("AMC", ["All AMCs"] + sorted(df["AMC"].unique().tolist()))
with fc4:
    view = st.radio("View", ["List View", "Family View"], horizontal=True, label_visibility="collapsed")

fdf = df.copy()
if search:
    s = search.lower()
    fdf = fdf[fdf["Fund"].str.lower().str.contains(s) | fdf["AMC"].str.lower().str.contains(s)
              | fdf["Category"].str.lower().str.contains(s)]
if cat_filter != "All Categories":
    fdf = fdf[fdf["Category"] == cat_filter]
if amc_filter != "All AMCs":
    fdf = fdf[fdf["AMC"] == amc_filter]

def render_table(data):
    hdr = st.columns([3, 1.1, 0.8, 0.8, 0.8, 1, 1.3])
    for col, label in zip(hdr, ["Fund / AMC", "Category", "1Y", "3Y", "5Y", "Health Score", "Overlap Impact"]):
        col.markdown(f"<span style='color:#6b7688;font-size:0.72rem;font-weight:700;text-transform:uppercase'>{label}</span>", unsafe_allow_html=True)
    for _, r in data.iterrows():
        c = st.columns([3, 1.1, 0.8, 0.8, 0.8, 1, 1.3])
        c[0].markdown(f"<div class='fund-name'>{r['Fund']}</div><div class='fund-amc'>{r['AMC']} Mutual Fund</div>", unsafe_allow_html=True)
        c[1].markdown(f"<span class='cat-dot'></span>{r['Category']}", unsafe_allow_html=True)
        def pct(v): return f"{v*100:.1f}%" if v is not None else "—"
        for col, key in zip(c[2:5], ["1Y", "3Y", "5Y"]):
            v = r[key]
            color = "#4ade80" if (v or 0) >= 0 else "#f87171"
            col.markdown(f"<span style='color:{color}'>{pct(v)}</span>", unsafe_allow_html=True)
        _, cls = score_bucket(r["Score"])
        c[5].markdown(f"<div class='score-circle {cls}'>{r['Score']}</div>", unsafe_allow_html=True)
        ov_pct_disp = f"{r['OverlapPct']:.1f}%" if r["OverlapPct"] is not None else "—"
        c[6].markdown(f"<span class='mfh-badge {r['OverlapCls']}'>{r['OverlapLabel']}</span><br>"
                       f"<span style='font-size:0.7rem;color:#6b7688'>{ov_pct_disp}</span>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:2px 0;border-color:#1c2333'>", unsafe_allow_html=True)

if view == "List View":
    render_table(fdf)
else:
    for amc, grp in fdf.groupby("AMC"):
        with st.expander(f"{amc} Mutual Fund · {len(grp)} fund(s) · avg score {grp['Score'].mean():.0f}"):
            render_table(grp)

st.markdown("---")
lc1, lc2, lc3 = st.columns(3)
lc1.markdown("**How we calculate MF Health Score**")
lc1.caption("Performance (25) · Consistency (20) · Overlap (20, when available) · Concentration (15) · Risk Adjusted (10). "
            "Cost (expense ratio) is not scored — no free per-fund data source found.")
lc2.markdown("**Overlap Impact**")
lc2.caption("Share of a fund's disclosed holdings that also appear in your other funds. Shown only when holdings data is available.")
lc3.markdown("🟢 80–100 Excellent &nbsp; 🟡 60–79 Good &nbsp; 🟠 40–59 Average &nbsp; 🔴 0–39 Poor")

st.caption("Mutual fund investments are subject to market risks. Past performance is not indicative of future returns.")
