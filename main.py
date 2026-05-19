#!/usr/bin/env python3
"""
Close CRM take-home script (Part 1).

Workflow:
  1. Read CSV (one row = one contact) with robust multiline parsing.
  2. Validate rows; log and discard invalid data.
  3. Group contacts by company name (company = lead in Close).
  4. Import leads and contacts via the Close API (tagged with a batch ID).
  5. Search Close for leads founded in the CLI date range.
  6. Filter to this import batch only (so test leads do not skew the report).
  7. Segment by US state and write output/report.csv.
  8. Run reconciliation: CSV expected vs Close API report.

Example:
    python main.py --csv "Customer Support Engineer Take Home Project - Import File - MOCK_DATA.csv" \\
        --start-date 1965-01-01 --end-date 2019-12-31
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
from close_api import CloseAPIClient, CloseAPIError
from csv_loader import load_csv_as_dataframe
from import_manifest import (
    company_names_from_manifest,
    generate_batch_id,
    load_manifest,
    save_manifest,
)
from lead_filter import filter_leads_for_import
from parsers import normalize_email_key, normalize_phone_key
from report_generator import (
    build_state_report,
    build_state_report_from_companies,
    companies_from_groups,
    write_report,
)
from validators import ValidatedRow, validate_row

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import CSV into Close CRM and build a state revenue report "
            "for leads founded in a date range."
        ),
    )
    parser.add_argument("--csv", required=True, help="Path to the import CSV file.")
    parser.add_argument(
        "--start-date",
        required=True,
        help="Founded-date range start (YYYY-MM-DD), inclusive.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Founded-date range end (YYYY-MM-DD), inclusive.",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Import batch tag (default: auto-generated per run).",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip CSV import; search Close and report using saved manifest.",
    )
    parser.add_argument(
        "--all-org-leads",
        action="store_true",
        help="Include all org leads in date range, not only this import batch.",
    )
    parser.add_argument(
        "--report-from-csv",
        action="store_true",
        help="DEV ONLY: skip Close API search for the report.",
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help="Skip post-run CSV vs API reconciliation.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def validate_cli_dates(start: str, end: str) -> None:
    fmt = "%Y-%m-%d"
    try:
        start_dt = datetime.strptime(start, fmt)
        end_dt = datetime.strptime(end, fmt)
    except ValueError as exc:
        raise ValueError("--start-date and --end-date must be YYYY-MM-DD") from exc
    if start_dt > end_dt:
        raise ValueError("--start-date must be on or before --end-date")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    aliases = {
        "company_name": "company",
        "contact_name": "contact name",
        "contact_emails": "contact emails",
        "contact_phones": "contact phones",
        "founded_date": "custom.company founded",
        "revenue": "custom.company revenue",
        "state": "company us state",
    }
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    missing = set(config.CSV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    return df


def log_invalid_row(message: str) -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with config.INVALID_ROWS_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")
    logger.warning(message)


def load_and_validate_csv(csv_path: Path) -> list[ValidatedRow]:
    """Read CSV (multiline-safe) and validate each row."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = normalize_columns(load_csv_as_dataframe(csv_path))
    valid_rows: list[ValidatedRow] = []
    invalid_count = 0

    for idx, row in df.iterrows():
        row_number = int(idx) + 2
        row_dict = {col: row.get(col, "") for col in config.CSV_COLUMNS}
        validated, error = validate_row(row_dict, row_number)
        if error:
            log_invalid_row(error)
            invalid_count += 1
            continue
        valid_rows.append(validated)

    logger.info(
        "CSV validation: %d valid rows, %d discarded (see %s)",
        len(valid_rows),
        invalid_count,
        config.INVALID_ROWS_LOG,
    )
    return valid_rows


def group_by_company(rows: list[ValidatedRow]) -> dict[str, list[ValidatedRow]]:
    groups: dict[str, list[ValidatedRow]] = defaultdict(list)
    for row in rows:
        groups[row.company_name].append(row)
    return dict(groups)


def merge_company_metadata(contacts: list[ValidatedRow]) -> ValidatedRow:
    """Best lead-level fields from all contact rows for one company."""
    meta = contacts[0]
    state = meta.state
    founded = meta.founded_date
    revenue = meta.revenue

    for row in contacts[1:]:
        if row.state:
            state = row.state
        if row.founded_date:
            founded = row.founded_date
        if row.revenue is not None:
            revenue = max(revenue, row.revenue) if revenue is not None else row.revenue

    meta.state = state
    meta.founded_date = founded
    meta.revenue = revenue
    return meta


def contact_display_name(row: ValidatedRow) -> str:
    if row.contact_name:
        return row.contact_name
    if row.emails:
        return row.emails[0].split("@")[0]
    return row.company_name


def contact_payload(row: ValidatedRow) -> dict:
    payload: dict = {"name": contact_display_name(row)}
    if row.emails:
        payload["emails"] = [{"email": e, "type": "office"} for e in row.emails]
    if row.phones:
        payload["phones"] = [{"phone": p, "type": "office"} for p in row.phones]
    return payload


def _contact_match_keys(contact: dict) -> set[str]:
    """Build email:/phone: keys for duplicate detection from a Close contact or payload."""
    keys: set[str] = set()
    for entry in contact.get("emails") or []:
        email = entry.get("email") if isinstance(entry, dict) else entry
        if email:
            keys.add(f"email:{normalize_email_key(str(email))}")
    for entry in contact.get("phones") or []:
        phone = entry.get("phone") if isinstance(entry, dict) else entry
        if phone:
            digits = normalize_phone_key(str(phone))
            if len(digits) >= 7:
                keys.add(f"phone:{digits}")
    return keys


def contact_already_on_lead(existing_keys: set[str], payload: dict) -> bool:
    """
    Return True when this CSV contact matches an existing lead contact.

    Matches on any shared email or phone (7+ digits). Name-only rows without
    email/phone are compared by normalized display name when no keys overlap.
    """
    new_keys = _contact_match_keys(payload)
    if new_keys:
        return bool(new_keys & existing_keys)

    name = (payload.get("name") or "").strip().lower()
    if not name:
        return False
    return f"name:{name}" in existing_keys


def _register_contact_keys(keys: set[str], contact: dict) -> None:
    """Add fingerprints from a contact dict into the running set."""
    keys.update(_contact_match_keys(contact))
    name = (contact.get("name") or "").strip().lower()
    if name:
        keys.add(f"name:{name}")


def import_companies(
    client: CloseAPIClient,
    groups: dict[str, list[ValidatedRow]],
    batch_id: str,
) -> None:
    """Create or update one lead per company; stamp batch ID for accurate reporting."""
    created = 0
    reused = 0
    contacts_added = 0
    contacts_skipped = 0

    for company_name, contacts in sorted(groups.items()):
        lead_meta = merge_company_metadata(contacts)

        try:
            existing = client.find_lead_by_name(company_name)
        except CloseAPIError as exc:
            logger.error("Lead search failed for '%s': %s", company_name, exc)
            continue

        if existing:
            lead_id = existing["id"]
            reused += 1
            try:
                client.update_lead(
                    lead_id,
                    state=lead_meta.state,
                    founded_date=lead_meta.founded_date,
                    revenue=lead_meta.revenue,
                    batch_id=batch_id,
                )
            except CloseAPIError as exc:
                logger.warning("Could not update lead '%s': %s", company_name, exc)
            try:
                on_lead = client.list_contacts_for_lead(lead_id)
            except CloseAPIError as exc:
                logger.warning(
                    "Could not list contacts for '%s'; may create duplicates: %s",
                    company_name,
                    exc,
                )
                on_lead = []
            existing_keys: set[str] = set()
            for contact in on_lead:
                _register_contact_keys(existing_keys, contact)
            contacts_to_add = contacts
        else:
            try:
                lead = client.create_lead(
                    company_name,
                    state=lead_meta.state,
                    founded_date=lead_meta.founded_date,
                    revenue=lead_meta.revenue,
                    batch_id=batch_id,
                    contacts=[contact_payload(contacts[0])],
                )
                lead_id = lead["id"]
                created += 1
                existing_keys = _contact_match_keys(contact_payload(contacts[0]))
                contacts_to_add = contacts[1:]
            except CloseAPIError as exc:
                logger.error("Failed to create lead '%s': %s", company_name, exc)
                continue

        for row in contacts_to_add:
            payload = contact_payload(row)
            if contact_already_on_lead(existing_keys, payload):
                contacts_skipped += 1
                logger.debug(
                    "Skipping duplicate contact '%s' on '%s'",
                    contact_display_name(row),
                    company_name,
                )
                continue
            try:
                client.create_contact(lead_id, payload)
                contacts_added += 1
                _register_contact_keys(existing_keys, payload)
            except CloseAPIError as exc:
                logger.error(
                    "Failed to create contact '%s' on '%s': %s",
                    contact_display_name(row),
                    company_name,
                    exc,
                )

    print(
        f"\nImport summary: {created} leads created, {reused} updated/reused, "
        f"{contacts_added} contacts added, {contacts_skipped} skipped (already on lead)."
    )
    print(f"Import batch ID: {batch_id}")


def run_report_from_api(
    client: CloseAPIClient,
    start_date: str,
    end_date: str,
    *,
    manifest_companies: set[str],
    batch_id: str | None,
    strict_import_filter: bool,
) -> pd.DataFrame:
    """Search Close API, filter to import batch, build report."""
    logger.info("Searching Close for leads founded %s to %s", start_date, end_date)
    leads = client.search_leads(start_date, end_date)

    before = len(leads)
    leads = filter_leads_for_import(
        leads,
        manifest_companies=manifest_companies,
        batch_id=batch_id,
        strict=strict_import_filter,
    )
    if strict_import_filter and before != len(leads):
        logger.info(
            "Import filter: %d leads in range -> %d from this batch/manifest",
            before,
            len(leads),
        )

    report_df = build_state_report(leads)
    write_report(report_df, config.REPORT_PATH)
    return report_df


def run_report_from_csv(
    groups: dict[str, list[ValidatedRow]],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    companies = companies_from_groups(groups)
    report_df = build_state_report_from_companies(companies, start_date, end_date)
    write_report(report_df, config.REPORT_PATH)
    return report_df


def run_reconciliation(
    csv_report: pd.DataFrame,
    api_report: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> bool:
    """Compare per-state lead counts; write output/reconciliation.csv."""
    from scripts.reconcile import build_reconciliation

    recon = build_reconciliation(csv_report, api_report, start_date, end_date)
    recon.to_csv(config.RECONCILE_REPORT_PATH, index=False)

    mismatches = recon[~recon["match"]] if not recon.empty else pd.DataFrame()
    if mismatches.empty:
        print("\nReconciliation: PASS — CSV and Close API reports match per state.")
        return True

    print("\nReconciliation: differences found (see output/reconciliation.csv):")
    print(mismatches.to_string(index=False))
    return False


def _print_report(report_df: pd.DataFrame) -> None:
    print(f"\nReport saved to: {config.REPORT_PATH}")
    if report_df.empty:
        print("No qualifying leads (need founded date in range, state, and revenue).")
    else:
        print(report_df.to_string(index=False))


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        validate_cli_dates(args.start_date, args.end_date)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = config.PROJECT_ROOT / csv_path

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if config.INVALID_ROWS_LOG.exists():
        config.INVALID_ROWS_LOG.write_text("", encoding="utf-8")

    batch_id = args.batch_id or generate_batch_id()
    strict_filter = not args.all_org_leads
    client = CloseAPIClient()
    groups: dict[str, list[ValidatedRow]] = {}
    manifest_companies: set[str] = set()

    # ----- Phase 1: Import ---------------------------------------------------
    if not args.skip_import:
        print("=== Phase 1: Validate CSV and import into Close ===")
        valid_rows = load_and_validate_csv(csv_path)
        if not valid_rows:
            logger.error("No valid rows to import. See %s", config.INVALID_ROWS_LOG)
            sys.exit(1)

        groups = group_by_company(valid_rows)
        manifest_companies = set(groups.keys())

        save_manifest(
            config.IMPORT_MANIFEST_PATH,
            batch_id=batch_id,
            companies=list(manifest_companies),
            csv_file=str(csv_path.name),
            start_date=args.start_date,
            end_date=args.end_date,
            valid_contact_rows=len(valid_rows),
        )

        print(
            f"Validated {len(valid_rows)} contact rows into "
            f"{len(groups)} companies (leads)."
        )
        import_companies(client, groups, batch_id)
    else:
        print("=== Phase 1 skipped (--skip-import) ===")
        manifest = load_manifest(config.IMPORT_MANIFEST_PATH)
        if manifest:
            batch_id = manifest.get("batch_id", batch_id)
            manifest_companies = company_names_from_manifest(manifest)
            logger.info(
                "Loaded manifest: %d companies, batch=%s",
                len(manifest_companies),
                batch_id,
            )
        valid_rows = load_and_validate_csv(csv_path)
        groups = group_by_company(valid_rows)

    # ----- Phase 2: Report ---------------------------------------------------
    print("\n=== Phase 2: Search Close and generate state report ===")

    csv_report = build_state_report_from_companies(
        companies_from_groups(groups),
        args.start_date,
        args.end_date,
    )

    if args.report_from_csv:
        print("WARNING: --report-from-csv uses CSV only (dev mode).")
        write_report(csv_report, config.REPORT_PATH)
        api_report = csv_report
    else:
        if not manifest_companies:
            manifest = load_manifest(config.IMPORT_MANIFEST_PATH)
            if manifest:
                manifest_companies = company_names_from_manifest(manifest)
                batch_id = manifest.get("batch_id", batch_id)

        api_report = run_report_from_api(
            client,
            args.start_date,
            args.end_date,
            manifest_companies=manifest_companies,
            batch_id=batch_id,
            strict_import_filter=strict_filter,
        )

    _print_report(api_report if not args.report_from_csv else csv_report)

    # ----- Phase 3: Reconciliation -----------------------------------------
    if not args.no_reconcile and not args.report_from_csv:
        print("\n=== Phase 3: Reconciliation (CSV vs Close API) ===")
        ok = run_reconciliation(
            csv_report,
            api_report,
            args.start_date,
            args.end_date,
        )
        if not ok:
            logger.warning(
                "Reports differ. Delete unrelated leads in Close or use import filter "
                "(default). See output/reconciliation.csv."
            )


if __name__ == "__main__":
    main()
