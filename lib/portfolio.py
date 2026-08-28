"""
Gradually move load_data(), FD/MF/stock/gold processing, metrics, integrity
from app.py into this module. Callers import from here.

For day 1: keep processing inside pages/1_Command_Center.py (copy from current
app.py), then extract functions one by one.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
from lib.config import EXCEL_PATH

def load_excel(uploaded_file=None):
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
    else:
        try:
            xls = pd.ExcelFile(EXCEL_PATH)
        except Exception:
            st.error(f"Could not load {EXCEL_PATH}")
            st.stop()
    sheet_map = {s.lower().strip(): s for s in xls.sheet_names}

    def find_sheet(*names):
        for n in names:
            if n in sheet_map:
                return sheet_map[n]
        return list(xls.sheet_names)[0]

    fd = pd.read_excel(xls, find_sheet("fd", "fixed deposits", "fixed_deposits"))
    mf = pd.read_excel(xls, find_sheet("mf", "mutual funds", "mutual_funds"))
    stocks = pd.read_excel(xls, find_sheet("stocks", "stock", "equities"))
    return fd, mf, stocks
