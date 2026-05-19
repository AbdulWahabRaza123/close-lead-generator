"""
Application configuration loaded from environment variables and sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Close API -----------------------------------------------------------------

CLOSE_API_BASE_URL = "https://api.close.com/api/v1"
CLOSE_API_KEY = os.getenv("CLOSE_API_KEY", "").strip()

# Custom field IDs matching take-home CSV column names in Close.
CLOSE_CF_FOUNDED_DATE = os.getenv("CLOSE_CF_FOUNDED_DATE", "").strip()
CLOSE_CF_REVENUE = os.getenv("CLOSE_CF_REVENUE", "").strip()

DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")

# --- Paths ---------------------------------------------------------------------

OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"
REPORT_PATH = OUTPUT_DIR / "report.csv"
IMPORT_MANIFEST_PATH = OUTPUT_DIR / "import_manifest.json"
RECONCILE_REPORT_PATH = OUTPUT_DIR / "reconciliation.csv"
INVALID_ROWS_LOG = LOGS_DIR / "invalid_rows.log"

# Take-home MOCK_DATA.csv headers (normalized to lowercase in main.py).
CSV_COLUMNS = [
    "company",
    "contact name",
    "contact emails",
    "contact phones",
    "custom.company founded",
    "custom.company revenue",
    "company us state",
]

# Default report window suggested for MOCK_DATA (override via CLI).
DEFAULT_START_DATE = "1965-01-01"
DEFAULT_END_DATE = "2019-12-31"

REQUEST_TIMEOUT = 30
