import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'store_intel.db'}")
POS_CSV_PATH = os.getenv(
    "POS_CSV_PATH",
    str(ROOT / "POS - sample transactionsb1e826f.csv"),
)
LAYOUT_PATH = os.getenv("LAYOUT_PATH", str(ROOT / "store_layout.json"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
STALE_FEED_MINUTES = int(os.getenv("STALE_FEED_MINUTES", "10"))
CONVERSION_WINDOW_MINUTES = int(os.getenv("CONVERSION_WINDOW_MINUTES", "5"))
