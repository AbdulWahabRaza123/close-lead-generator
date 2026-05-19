"""
Row-level validation for the Close take-home MOCK_DATA CSV format.

Rules are derived from the import file and sample output:
- Company name is required for every row.
- A contact row must have at least one valid email OR one valid phone.
- Contact name is optional (Close allows unnamed contacts when email/phone exists).
- Founded date, revenue, and state are parsed when present; missing values may still
  import but exclude the company from the date-filtered state revenue report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from parsers import (
    parse_founded_date,
    parse_revenue,
    parse_valid_emails,
    parse_valid_phones,
)


@dataclass
class ValidatedRow:
    """Normalized row ready for grouping and Close API import."""

    company_name: str
    contact_name: Optional[str]
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    founded_date: Optional[str] = None  # ISO YYYY-MM-DD
    revenue: Optional[float] = None
    state: Optional[str] = None  # Full US state name, e.g. California
    source_row: int = 0


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip() == ""


def normalize_raw_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Map take-home CSV headers to internal keys.

    Supports both MOCK_DATA headers and the simplified sample_input headers.
    """
    key_map = {
        "company": "company_name",
        "contact name": "contact_name",
        "contact emails": "contact_emails",
        "contact phones": "contact_phones",
        "custom.company founded": "founded_raw",
        "custom.company revenue": "revenue_raw",
        "company us state": "state",
        # Simplified aliases from earlier scaffold.
        "company_name": "company_name",
        "contact_name": "contact_name",
        "email": "contact_emails",
        "founded_date": "founded_raw",
        "revenue": "revenue_raw",
    }

    normalized: dict[str, Any] = {}
    for key, value in row.items():
        internal = key_map.get(str(key).strip().lower())
        if internal:
            normalized[internal] = value

    return normalized


def validate_row(
    row: dict[str, Any],
    row_number: int,
) -> tuple[Optional[ValidatedRow], Optional[str]]:
    """
    Validate one CSV row.

    Returns (ValidatedRow, None) on success, (None, error_message) on failure.
    """
    data = normalize_raw_row(row)

    if _is_blank(data.get("company_name")):
        return None, f"Row {row_number}: Company is required"

    company_name = str(data["company_name"]).strip()
    contact_name = (
        str(data["contact_name"]).strip() if not _is_blank(data.get("contact_name")) else None
    )

    emails = parse_valid_emails(data.get("contact_emails", ""))
    phones = parse_valid_phones(data.get("contact_phones", ""))

    if not emails and not phones:
        return None, (
            f"Row {row_number}: at least one valid Contact Email or Contact Phone is required"
        )

    founded_date = parse_founded_date(data.get("founded_raw", ""))
    revenue = parse_revenue(data.get("revenue_raw", ""))

    state: Optional[str] = None
    if not _is_blank(data.get("state")):
        from state_utils import to_full_name

        state = to_full_name(str(data["state"]).strip())

    return (
        ValidatedRow(
            company_name=company_name,
            contact_name=contact_name,
            emails=emails,
            phones=phones,
            founded_date=founded_date,
            revenue=revenue,
            state=state,
            source_row=row_number,
        ),
        None,
    )
