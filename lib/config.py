from pathlib import Path
import pytz
from datetime import datetime

IST = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.now(IST)
TODAY_STR = NOW_IST.strftime("%Y-%m-%d")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HISTORY_PATH = DATA_DIR / "history.csv"
AMFI_CACHE_PATH = DATA_DIR / "amfi_nav_cache.json"
EXCEL_PATH = DATA_DIR / "Networth_Raw_Data.xlsx"

# Optional: set in Streamlit secrets for durable history later
# [history]
# backend = "sheet"   # or "supabase" | "file"
