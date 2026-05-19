"""
Robust CSV loading for the take-home import file.

Uses Python's csv module so multiline quoted fields (phones/emails) parse correctly.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

import config


def load_csv_as_dataframe(csv_path: Path) -> pd.DataFrame:
    """
    Read the import CSV into a DataFrame with normalized lowercase column names.

    Multiline cells (e.g. phone numbers spanning two lines) are handled by csv.DictReader.
    """
    rows: list[dict[str, str]] = []

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header row: {csv_path}")

        for raw in reader:
            normalized: dict[str, str] = {}
            for key, value in raw.items():
                if key is None:
                    continue
                col = key.strip().lower()
                # Preserve empty string instead of None for downstream validators.
                normalized[col] = (value if value is not None else "").strip()
            rows.append(normalized)

    if not rows:
        return pd.DataFrame(columns=config.CSV_COLUMNS)

    return pd.DataFrame(rows)
