"""
Build the state-segmented CSV report matching the take-home sample output format.

Sample columns:
  US State, Total number of leads, The lead with most revenue, Total revenue, Median revenue
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from statistics import median
from typing import Any, Optional

import pandas as pd

from close_api import extract_revenue, extract_state
from parsers import format_currency

logger = logging.getLogger(__name__)

# Output headers aligned with "Sample Output - Sheet1.csv".
REPORT_COLUMNS = [
    "US State",
    "Total number of leads",
    "The lead with most revenue",
    "Total revenue",
    "Median revenue",
]


@dataclass
class CompanyLead:
    """One lead (company) used for reporting."""

    name: str
    state: Optional[str] = None
    founded_date: Optional[str] = None  # ISO YYYY-MM-DD
    revenue: Optional[float] = None


def companies_from_groups(
    groups: dict[str, list[Any]],
) -> list[CompanyLead]:
    """
    Build one CompanyLead per company from grouped validated rows.

    When rows disagree: use any non-empty state/founded; use the maximum revenue seen.
    """
    companies: list[CompanyLead] = []

    for company_name, rows in groups.items():
        state: Optional[str] = None
        founded: Optional[str] = None
        revenue: Optional[float] = None

        for row in rows:
            if row.state:
                state = row.state
            if row.founded_date:
                founded = row.founded_date
            if row.revenue is not None:
                revenue = max(revenue, row.revenue) if revenue is not None else row.revenue

        companies.append(
            CompanyLead(
                name=company_name,
                state=state,
                founded_date=founded,
                revenue=revenue,
            )
        )

    return companies


def filter_companies_for_report(
    companies: list[CompanyLead],
    start_date: str,
    end_date: str,
) -> list[CompanyLead]:
    """
    Keep leads that qualify for the state revenue report.

    Requirements (from sample output semantics):
    - founded date within [start_date, end_date]
    - US state present
    - revenue present
    """
    qualified: list[CompanyLead] = []

    for company in companies:
        if not company.state:
            logger.debug("Exclude %s: missing state", company.name)
            continue
        if company.revenue is None:
            logger.debug("Exclude %s: missing revenue", company.name)
            continue
        if not company.founded_date:
            logger.debug("Exclude %s: missing founded date", company.name)
            continue
        if not (start_date <= company.founded_date <= end_date):
            logger.debug(
                "Exclude %s: founded %s outside %s..%s",
                company.name,
                company.founded_date,
                start_date,
                end_date,
            )
            continue
        qualified.append(company)

    return qualified


def build_state_report_from_companies(
    companies: list[CompanyLead],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Generate report from in-memory company records (CSV / import path)."""
    qualified = filter_companies_for_report(companies, start_date, end_date)
    return _aggregate_by_state(qualified)


def build_state_report(leads: list[dict[str, Any]]) -> pd.DataFrame:
    """Generate report from Close API lead objects (--skip-import path)."""
    companies: list[CompanyLead] = []

    for lead in leads:
        name = lead.get("display_name") or lead.get("name") or lead.get("id", "Unknown")
        state = extract_state(lead)
        revenue = extract_revenue(lead)
        founded = _founded_from_api_lead(lead)

        if not state or revenue is None or not founded:
            logger.warning("Skipping lead missing report fields: %s", name)
            continue

        companies.append(
            CompanyLead(name=name, state=state, founded_date=founded, revenue=revenue)
        )

    return _aggregate_by_state(companies)


def _founded_from_api_lead(lead: dict[str, Any]) -> Optional[str]:
    from close_api import extract_founded_date

    return extract_founded_date(lead)


def _aggregate_by_state(companies: list[CompanyLead]) -> pd.DataFrame:
    """Group qualified companies by state and compute metrics."""
    by_state: dict[str, list[tuple[str, float]]] = {}

    for company in companies:
        assert company.state is not None and company.revenue is not None
        by_state.setdefault(company.state, []).append((company.name, company.revenue))

    rows: list[dict[str, Any]] = []
    for state in sorted(by_state.keys()):
        entries = by_state[state]
        revenues = [r for _, r in entries]
        top_name, _ = max(entries, key=lambda item: item[1])
        total = sum(revenues)
        med = median(revenues)

        rows.append(
            {
                "US State": state,
                "Total number of leads": len(entries),
                "The lead with most revenue": top_name,
                "Total revenue": format_currency(total),
                "Median revenue": format_currency(med),
            }
        )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def write_report(df: pd.DataFrame, output_path) -> None:
    """Write report CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Report written to %s (%d states)", output_path, len(df))
