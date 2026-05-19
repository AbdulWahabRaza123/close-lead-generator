#!/usr/bin/env python3
"""
Compare CSV-expected report vs Close API report (per state).

Used by main.py after import; can also be run standalone:
    python testfiles/scripts/reconcile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from close_api import CloseAPIClient  # noqa: E402
from import_manifest import company_names_from_manifest, load_manifest  # noqa: E402
from lead_filter import filter_leads_for_import  # noqa: E402
from main import group_by_company, load_and_validate_csv  # noqa: E402
from report_generator import (  # noqa: E402
    build_state_report,
    build_state_report_from_companies,
    companies_from_groups,
)


def build_reconciliation(
    csv_report: pd.DataFrame,
    api_report: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Build a per-state diff table."""
    def _index(df: pd.DataFrame) -> dict[str, dict]:
        if df.empty:
            return {}
        return {
            row["US State"]: row.to_dict()
            for _, row in df.iterrows()
        }

    csv_by = _index(csv_report)
    api_by = _index(api_report)
    states = sorted(set(csv_by.keys()) | set(api_by.keys()))

    rows = []
    for state in states:
        c = csv_by.get(state, {})
        a = api_by.get(state, {})
        c_count = int(c.get("Total number of leads", 0) or 0)
        a_count = int(a.get("Total number of leads", 0) or 0)
        rows.append(
            {
                "US State": state,
                "csv_leads": c_count,
                "api_leads": a_count,
                "match": c_count == a_count,
                "csv_top_revenue_lead": c.get("The lead with most revenue", ""),
                "api_top_revenue_lead": a.get("The lead with most revenue", ""),
                "csv_total_revenue": c.get("Total revenue", ""),
                "api_total_revenue": a.get("Total revenue", ""),
                "date_range": f"{start_date} to {end_date}",
            }
        )

    return pd.DataFrame(rows)


def main() -> int:
    manifest = load_manifest(config.IMPORT_MANIFEST_PATH)
    if not manifest:
        print("No import manifest found. Run main.py import first.")
        return 1

    csv_name = manifest.get("csv_file", "")
    csv_path = config.PROJECT_ROOT / csv_name
    start = manifest["start_date"]
    end = manifest["end_date"]
    batch_id = manifest.get("batch_id")

    valid = load_and_validate_csv(csv_path)
    groups = group_by_company(valid)
    csv_report = build_state_report_from_companies(
        companies_from_groups(groups), start, end
    )

    client = CloseAPIClient()
    leads = client.search_leads(start, end)
    leads = filter_leads_for_import(
        leads,
        manifest_companies=company_names_from_manifest(manifest),
        batch_id=batch_id,
        strict=True,
    )
    api_report = build_state_report(leads)

    recon = build_reconciliation(csv_report, api_report, start, end)
    recon.to_csv(config.RECONCILE_REPORT_PATH, index=False)

    print("CSV report total leads:", int(csv_report["Total number of leads"].sum()))
    print("API report total leads:", int(api_report["Total number of leads"].sum()))
    print(recon.to_string(index=False))
    print(f"\nWritten: {config.RECONCILE_REPORT_PATH}")

    return 0 if recon["match"].all() else 1


if __name__ == "__main__":
    sys.exit(main())
