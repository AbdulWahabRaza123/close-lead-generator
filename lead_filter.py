"""
Filter Close API leads so reports only include leads from the current import batch.
"""

from __future__ import annotations

from typing import Any, Optional

from close_api import extract_batch_id


def lead_matches_import(
    lead: dict[str, Any],
    *,
    manifest_companies: set[str],
    batch_id: Optional[str],
) -> bool:
    """
    Return True when a lead belongs to this import run.

    Matches if the company name is in the manifest OR the lead description has the batch tag.
    """
    name = lead.get("name") or ""
    display = lead.get("display_name") or ""

    if manifest_companies:
        if name in manifest_companies or display in manifest_companies:
            return True

    if batch_id and extract_batch_id(lead) == batch_id:
        return True

    return False


def filter_leads_for_import(
    leads: list[dict[str, Any]],
    *,
    manifest_companies: set[str],
    batch_id: Optional[str],
    strict: bool,
) -> list[dict[str, Any]]:
    """
    When strict=True, keep only leads from this import (manifest / batch).
    When strict=False, return all leads unchanged.
    """
    if not strict:
        return leads

    if not manifest_companies and not batch_id:
        return leads

    filtered = [
        lead
        for lead in leads
        if lead_matches_import(lead, manifest_companies=manifest_companies, batch_id=batch_id)
    ]
    return filtered
