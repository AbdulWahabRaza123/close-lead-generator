"""
Track which companies were imported in each run for accurate API reporting.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def generate_batch_id() -> str:
    """Unique batch tag stamped on every lead created/updated in one run."""
    return datetime.now(timezone.utc).strftime("takehome_%Y%m%d_%H%M%S")


def save_manifest(
    path: Path,
    *,
    batch_id: str,
    companies: list[str],
    csv_file: str,
    start_date: str,
    end_date: str,
    valid_contact_rows: int,
) -> None:
    """Persist import manifest so Phase 2 can filter API results to this run only."""
    payload: dict[str, Any] = {
        "batch_id": batch_id,
        "companies": sorted(set(companies)),
        "csv_file": csv_file,
        "start_date": start_date,
        "end_date": end_date,
        "valid_contact_rows": valid_contact_rows,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any] | None:
    """Load manifest if present; return None when file does not exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def company_names_from_manifest(manifest: dict[str, Any]) -> set[str]:
    """Company names imported in the batch (used to filter API search results)."""
    return set(manifest.get("companies") or [])
