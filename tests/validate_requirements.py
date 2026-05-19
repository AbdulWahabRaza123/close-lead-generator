#!/usr/bin/env python3
"""Quick static check that required modules and columns exist."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from report_generator import REPORT_COLUMNS  # noqa: E402

SAMPLE_COLUMNS = [
    "US State",
    "Total number of leads",
    "The lead with most revenue",
    "Total revenue",
    "Median revenue",
]

REQUIRED_MODULES = [
    "main.py",
    "close_api.py",
    "validators.py",
    "parsers.py",
    "report_generator.py",
    "config.py",
    "requirements.txt",
    "README.md",
]


def main() -> int:
    errors: list[str] = []

    for name in REQUIRED_MODULES:
        if not (ROOT / name).exists():
            errors.append(f"Missing file: {name}")

    if REPORT_COLUMNS != SAMPLE_COLUMNS:
        errors.append(f"Report columns mismatch: {REPORT_COLUMNS} != {SAMPLE_COLUMNS}")

    if len(config.CSV_COLUMNS) < 7:
        errors.append("CSV_COLUMNS incomplete")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    print("PASS: All requirement artifacts present.")
    print(f"  Report columns: {REPORT_COLUMNS}")
    print(f"  CSV columns: {config.CSV_COLUMNS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
