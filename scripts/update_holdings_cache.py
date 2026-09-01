import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXCEL = DATA / "Networth_Raw_Data.xlsx"
AMFI_CACHE = DATA / "amfi_nav_cache.json"
HOLDINGS_CACHE = DATA / "mf_holdings_cache.json"


def normalize_holdings(raw):
    out = []
    if isinstance(raw, dict):
        raw = raw.get("equity") or raw.get("holdings") or []
    for h in raw or []:
        if not isinstance(h, dict):
            continue
        name = h.get("name") or h.get("stock_name") or h.get("instrument") or h.get("security")
        w = h.get("weight_pct") or h.get("weight") or h.get("pct") or h.get("percentage")
        if name and w is not None:
            try:
                out.append({"name": str(name).strip(), "weight": float(w)})
            except Exception:
                continue
    return out[:20]


def main():
    amfi = json.loads(AMFI_CACHE.read_text())
    code_map = amfi.get("code", {})

    mf = pd.read_excel(EXCEL, sheet_name="MF")
    isins = mf["ISIN"].dropna().astype(str).unique().tolist()
    codes = sorted({int(code_map[isin]) for isin in isins if isin in code_map})
    print(f"Resolved {len(codes)} scheme codes")

    cache = json.loads(HOLDINGS_CACHE.read_text()) if HOLDINGS_CACHE.exists() else {}

    for i in range(0, len(codes), 10):
        chunk = codes[i:i + 10]
        try:
            r = requests.get(
                "https://mfdata.in/api/v1/compare",
                params={"scheme_codes": ",".join(str(c) for c in chunk)},
                timeout=30,
            )
            if r.status_code != 200:
                print(f"chunk {chunk}: HTTP {r.status_code}")
                continue
            payload = r.json()
            data = payload.get("data") or payload
            entries = data if isinstance(data, list) else data.get("schemes", [])
            for entry in entries:
                code = entry.get("scheme_code") or entry.get("code")
                if code is None:
                    continue
                raw = entry.get("top_holdings") or entry.get("holdings") or entry.get("equity_holdings") or []
                holdings = normalize_holdings(raw)
                if holdings:
                    cache[str(int(code))] = {"holdings": holdings, "fetched_at": datetime.now().isoformat()}
                    print(f"  {code}: {len(holdings)} holdings")
        except Exception as e:
            print(f"chunk {chunk} failed: {e}")

    HOLDINGS_CACHE.write_text(json.dumps(cache))
    print(f"Wrote {len(cache)} funds to {HOLDINGS_CACHE}")


if __name__ == "__main__":
    main()
