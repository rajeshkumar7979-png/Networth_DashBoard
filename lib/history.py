from __future__ import annotations
import os
from pathlib import Path
import pandas as pd
import streamlit as st
from lib.config import HISTORY_PATH, DATA_DIR, TODAY_STR

COLS = ["date", "net_worth", "equity_pct", "fd_pct", "pnl", "health_score"]

def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    df["date"] = df["date"].astype(str)
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    for c in COLS[1:]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["net_worth"])
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

def load_history() -> pd.DataFrame:
    _ensure_dir()
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=COLS)
    try:
        return _clean(pd.read_csv(HISTORY_PATH))
    except Exception:
        return pd.DataFrame(columns=COLS)

def log_snapshot(
    net_worth: float,
    equity_pct: float,
    fd_pct: float,
    pnl: float,
    health_score: float,
) -> pd.DataFrame:
    """Upsert today's row. Still uses local file — ephemeral on Streamlit Cloud.
    Swap body later for Google Sheet / Supabase without changing callers.
    """
    _ensure_dir()
    row = {
        "date": TODAY_STR,
        "net_worth": float(net_worth),
        "equity_pct": float(equity_pct),
        "fd_pct": float(fd_pct),
        "pnl": float(pnl),
        "health_score": round(float(health_score), 1),
    }
    hist = load_history()
    hist = hist[hist["date"] != TODAY_STR]
    hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    hist = _clean(hist)
    try:
        hist.to_csv(HISTORY_PATH, index=False)
    except Exception as e:
        st.warning(f"Could not write history: {e}")
    return hist

def merge_uploaded(csv_file) -> pd.DataFrame:
    incoming = pd.read_csv(csv_file)
    if "date" not in incoming.columns or "net_worth" not in incoming.columns:
        raise ValueError("CSV must have at least date and net_worth columns.")
    existing = load_history()
    merged = pd.concat([existing, incoming], ignore_index=True)
    merged = _clean(merged)
    merged.to_csv(HISTORY_PATH, index=False)
    return merged
