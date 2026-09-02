# scripts/update_holdings_cache.py
"""Refresh complete MF holdings for funds present in Networth_Raw_Data.xlsx.

Phase 1 rules:
- Resolve AMFI scheme code from the portfolio's ISIN using official AMFI NAVAll.
- Prefer AMC-statutory holdings via fund-disclosures.
- Fall back to mfdata.in family holdings.
- Never truncate holdings to top-N.
- Never replace a previously good cache entry with an empty/failed response.
- Write per-fund provenance/quality metadata separately.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.mf_holdings import (  # noqa: E402
    HOLDINGS_CACHE,
    HOLDINGS_META_CACHE,
    build_isin_index,
    fetch_amfi_universe,
    ingest_scheme_holdings,
    load_json,
    save_json_atomic,
)

RAW_XLSX = ROOT / "data" / "Networth_Raw_Data.xlsx"

ISIN_ALIASES = {"isin", "isin code", "isin number", "isin no", "isin id"}
FUND_ALIASES = {"fund name", "mutual fund", "scheme name", "scheme", "fund"}


def _norm_col(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _find_column(columns, aliases):
    normalized = {_norm_col(c): c for c in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    # relaxed contains match
    for norm, original in normalized.items():
        if any(alias in norm for alias in aliases):
            return original
    return None


def discover_mf_rows() -> pd.DataFrame:
    if not RAW_XLSX.exists():
        raise FileNotFoundError(f"Missing {RAW_XLSX}")

    xls = pd.ExcelFile(RAW_XLSX)
    candidates: List[pd.DataFrame] = []

    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(RAW_XLSX, sheet_name=sheet)
        except Exception:
            continue
        if df.empty:
            continue

        isin_col = _find_column(df.columns, ISIN_ALIASES)
        fund_col = _find_column(df.columns, FUND_ALIASES)
        if not isin_col:
            continue

        out = pd.DataFrame({
            "isin": df[isin_col].astype(str).str.strip().str.upper(),
            "fund_name": df[fund_col].astype(str).str.strip() if fund_col else "",
            "sheet": sheet,
        })
        out = out[out["isin"].str.match(r"^IN[A-Z0-9]{8,}$", na=False)]
        if not out.empty:
            candidates.append(out)

    if not candidates:
        raise RuntimeError("Could not find an ISIN column in any workbook sheet")

    result = pd.concat(candidates, ignore_index=True)
    result = result.drop_duplicates(subset=["isin"], keep="first")
    return result


def choose_scheme(isin: str, fund_name: str, isin_index: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any] | None:
    candidates = isin_index.get(isin.upper(), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Exact fund-name match wins. ISIN is already the primary identity key.
    fn = " ".join(str(fund_name or "").lower().replace("-", " ").split())
    scored = []
    for row in candidates:
        sn = " ".join(str(row.get("scheme_name") or "").lower().replace("-", " ").split())
        score = 0
        if fn and (fn in sn or sn in fn):
            score += 100
        if "direct" in fn and "direct" in sn:
            score += 10
        if "regular" in fn and "regular" in sn:
            score += 10
        if "growth" in fn and "growth" in sn:
            score += 5
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def main() -> int:
    print("=== MF holdings refresh: Phase 1 ===")
    print(f"Workbook: {RAW_XLSX}")

    portfolio = discover_mf_rows()
    print(f"Unique portfolio ISINs found: {len(portfolio)}")

    session = requests.Session()
    amfi_rows = fetch_amfi_universe(session, force=True)
    isin_index = build_isin_index(amfi_rows)
    print(f"AMFI universe rows: {len(amfi_rows)}")

    cache = load_json(HOLDINGS_CACHE, {})
    meta = load_json(HOLDINGS_META_CACHE, {})
    if not isinstance(cache, dict):
        cache = {}
    if not isinstance(meta, dict):
        meta = {}

    success = 0
    failed = 0
    unresolved = 0

    for _, row in portfolio.iterrows():
        isin = str(row["isin"]).strip().upper()
        fund_name = str(row.get("fund_name") or "").strip()
        scheme = choose_scheme(isin, fund_name, isin_index)

        if not scheme:
            unresolved += 1
            meta[isin] = {
                "status": "UNRESOLVED_AMFI",
                "isin": isin,
                "fund_name": fund_name,
                "updated_at": pd.Timestamp.utcnow().isoformat(),
            }
            print(f"[UNRESOLVED] {fund_name} | {isin}")
            continue

        scheme_code = str(scheme["scheme_code"])
        display_name = scheme.get("scheme_name") or fund_name
        print(f"[FETCH] {display_name} | {isin} | AMFI {scheme_code}")

        try:
            holdings, source_meta = ingest_scheme_holdings(session, scheme_code)
            if not holdings:
                raise RuntimeError("Source returned empty holdings")

            # IMPORTANT: preserve the old entry if a future source unexpectedly
            # returns an empty dataset. Successful non-empty data replaces it.
            cache[scheme_code] = holdings
            validation = source_meta.get("validation", {})
            meta[scheme_code] = {
                "status": "OK",
                "isin": isin,
                "fund_name": fund_name,
                "amfi_scheme_code": scheme_code,
                "amfi_scheme_name": display_name,
                "amc": scheme.get("amc"),
                "category": scheme.get("category"),
                **source_meta,
                "validation": validation,
            }
            success += 1
            print(f"  -> {len(holdings)} complete holdings | {source_meta.get('source')} | {validation.get('weight_check')}")
        except Exception as exc:
            failed += 1
            # Do NOT erase a previous good cache entry.
            meta[scheme_code] = {
                **(meta.get(scheme_code) if isinstance(meta.get(scheme_code), dict) else {}),
                "status": "ERROR",
                "isin": isin,
                "fund_name": fund_name,
                "amfi_scheme_code": scheme_code,
                "amfi_scheme_name": display_name,
                "error": str(exc),
                "updated_at": pd.Timestamp.utcnow().isoformat(),
                "cache_preserved": scheme_code in cache,
            }
            print(f"  !! FAILED: {exc}")

    save_json_atomic(HOLDINGS_CACHE, cache)
    save_json_atomic(HOLDINGS_META_CACHE, meta)

    print("\n=== RESULT ===")
    print(f"Successful:  {success}")
    print(f"Failed:      {failed}")
    print(f"Unresolved:  {unresolved}")
    print(f"Cache funds: {len([k for k in cache if str(k).isdigit()])}")
    print(f"Holdings cache: {HOLDINGS_CACHE}")
    print(f"Metadata:       {HOLDINGS_META_CACHE}")

    # Fail the GitHub Action only if absolutely nothing succeeded and no prior
    # cache exists. A partial outage should not destroy the deployed app.
    if success == 0 and not cache:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
