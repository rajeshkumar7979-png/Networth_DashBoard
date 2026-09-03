import numpy as np
import pandas as pd

def safe_float(val, default=0.0):
    try:
        v = pd.to_numeric(val, errors="coerce")
        return default if pd.isna(v) else float(v)
    except Exception:
        return default

def format_inr_indian(num, decimals=0):
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return "₹0" if decimals == 0 else "₹0.00"
    try:
        n = float(num)
    except Exception:
        return "₹0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if decimals <= 0:
        int_part = str(int(round(n)))
        frac = ""
    else:
        s = f"{n:.{decimals}f}"
        int_part, frac = s.split(".")
        frac = "." + frac
    if len(int_part) <= 3:
        grouped = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(reversed(groups)) + "," + last3
    return f"{sign}₹{grouped}{frac}"

def format_inr(num):
    return format_inr_indian(num, decimals=0)

def format_inr_compact(num):
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return "₹0"
    try:
        n = float(num)
    except Exception:
        return "₹0"
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1e7:
        return f"{sign}₹{a/1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a/1e5:.2f} L"
    return format_inr_indian(n, decimals=0)
