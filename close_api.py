"""
Thin wrapper around the Close CRM REST API.

Provides reusable methods for lead/contact creation and lead search.
Authentication uses HTTP Basic Auth with the API key as username (per Close docs).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

import config
from state_utils import to_abbrev, to_full_name

logger = logging.getLogger(__name__)


class CloseAPIError(Exception):
    """Raised when the Close API returns a non-success response."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class CloseAPIClient:
    """
    Client for Close CRM API v1.

    All network I/O is centralized here so main.py stays orchestration-focused.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = config.CLOSE_API_BASE_URL,
        dry_run: bool = config.DRY_RUN,
    ):
        self.api_key = (api_key or config.CLOSE_API_KEY).strip()
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        # In-memory leads/contacts during DRY_RUN so import dedup works offline.
        self._dry_run_leads: list[dict[str, Any]] = []
        self._dry_run_contacts: dict[str, list[dict[str, Any]]] = {}
        self._session = requests.Session()
        if self.api_key:
            self._session.auth = HTTPBasicAuth(self.api_key, "")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request and return parsed JSON or raise CloseAPIError."""
        url = f"{self.base_url}/{path.lstrip('/')}"

        if self.dry_run:
            # Synthetic responses keep the import/report flow testable without credentials.
            logger.info("DRY_RUN: %s %s", method.upper(), url)
            return self._dry_run_response(method, path, json=json)

        if not self.api_key:
            raise CloseAPIError(
                "CLOSE_API_KEY is not set. Copy .env.example to .env and add your key."
            )

        try:
            response = self._session.request(
                method,
                url,
                json=json,
                params=params,
                timeout=config.REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CloseAPIError(f"Network error calling Close API: {exc}") from exc

        if not response.ok:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise CloseAPIError(
                f"Close API error ({response.status_code}): {body}",
                status_code=response.status_code,
                payload=body,
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _dry_run_response(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Return minimal stub payloads when DRY_RUN is enabled."""
        if method.upper() == "POST" and path.startswith("lead"):
            payload = json or {}
            name = payload.get("name", "Dry Run Lead")
            lead = {
                "id": f"lead_{uuid.uuid4().hex[:12]}",
                "name": name,
                "display_name": name,
                "addresses": payload.get("addresses", []),
                "description": payload.get("description", ""),
                "custom": {},
            }
            self._dry_run_leads.append(lead)
            lead_id = lead["id"]
            for contact in payload.get("contacts") or []:
                self._dry_run_contacts.setdefault(lead_id, []).append(
                    {
                        "id": f"cont_{uuid.uuid4().hex[:12]}",
                        "lead_id": lead_id,
                        "name": contact.get("name"),
                        "emails": contact.get("emails", []),
                        "phones": contact.get("phones", []),
                    }
                )
            return lead
        if method.upper() == "POST" and path.startswith("contact"):
            lead_id = (json or {}).get("lead_id", "")
            contact = {
                "id": f"cont_{uuid.uuid4().hex[:12]}",
                "lead_id": lead_id,
                "name": (json or {}).get("name"),
                "emails": (json or {}).get("emails", []),
                "phones": (json or {}).get("phones", []),
            }
            self._dry_run_contacts.setdefault(lead_id, []).append(contact)
            return contact
        if method.upper() == "POST" and "data/search" in path:
            return {"data": [], "cursor": None}
        if method.upper() == "PUT" and path.startswith("lead/"):
            lead_id = path.split("/")[1].rstrip("/")
            for lead in self._dry_run_leads:
                if lead["id"] == lead_id:
                    if json:
                        lead["description"] = json.get("description", lead.get("description", ""))
                        if json.get("addresses"):
                            lead["addresses"] = json["addresses"]
                    return lead
            return {"id": lead_id, "description": (json or {}).get("description", "")}
        if method.upper() == "GET" and path.startswith("lead"):
            return {"data": list(self._dry_run_leads), "has_more": False}
        return {}

    # ---------------------------------------------------------------------------
    # Public API helpers (required by assessment)
    # ---------------------------------------------------------------------------

    def create_lead(
        self,
        company_name: str,
        *,
        state: Optional[str] = None,
        founded_date: Optional[str] = None,
        revenue: Optional[float] = None,
        batch_id: Optional[str] = None,
        contacts: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Create a Close Lead (one per company).

        Contacts may be nested on create; additional contacts can be added via create_contact().
        Founded date and revenue map to custom fields when configured in .env.
        """
        payload: dict[str, Any] = {"name": company_name}

        if state:
            # Close often stores/returns USPS abbreviations; we keep full name in description.
            payload["addresses"] = [
                {
                    "label": "business",
                    "state": to_abbrev(state),
                    "country": "US",
                }
            ]

        if config.CLOSE_CF_FOUNDED_DATE and founded_date:
            payload[f"custom.{config.CLOSE_CF_FOUNDED_DATE}"] = founded_date
        if config.CLOSE_CF_REVENUE and revenue is not None:
            payload[f"custom.{config.CLOSE_CF_REVENUE}"] = revenue

        payload["description"] = build_lead_description(
            founded_date=founded_date,
            revenue=revenue,
            state=state,
            batch_id=batch_id,
        )

        if contacts:
            payload["contacts"] = contacts

        logger.info("Creating lead: %s", company_name)
        return self._request("POST", "lead/", json=payload)

    def update_lead(
        self,
        lead_id: str,
        *,
        state: Optional[str] = None,
        founded_date: Optional[str] = None,
        revenue: Optional[float] = None,
        batch_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Update lead metadata when reusing an existing company (re-import / batch stamp).
        """
        payload: dict[str, Any] = {
            "description": build_lead_description(
                founded_date=founded_date,
                revenue=revenue,
                state=state,
                batch_id=batch_id,
            ),
        }
        if state:
            payload["addresses"] = [
                {"label": "business", "state": to_abbrev(state), "country": "US"}
            ]
        if config.CLOSE_CF_FOUNDED_DATE and founded_date:
            payload[f"custom.{config.CLOSE_CF_FOUNDED_DATE}"] = founded_date
        if config.CLOSE_CF_REVENUE and revenue is not None:
            payload[f"custom.{config.CLOSE_CF_REVENUE}"] = revenue

        logger.info("Updating lead %s with batch/metadata", lead_id)
        return self._request("PUT", f"lead/{lead_id}/", json=payload)

    def create_contact(
        self,
        lead_id: str,
        contact_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Attach a contact to an existing lead (name, emails, and/or phones)."""
        payload = {"lead_id": lead_id, **contact_payload}
        logger.info(
            "Creating contact '%s' on lead %s",
            contact_payload.get("name", "Contact"),
            lead_id,
        )
        return self._request("POST", "contact/", json=payload)

    def list_contacts_for_lead(self, lead_id: str) -> list[dict[str, Any]]:
        """Return all contacts on a lead (used to skip duplicates on re-import)."""
        if self.dry_run:
            return list(self._dry_run_contacts.get(lead_id, []))

        contacts: list[dict[str, Any]] = []
        skip = 0
        limit = 100

        while True:
            result = self._request(
                "GET",
                "contact/",
                params={
                    "lead_id": lead_id,
                    "_limit": limit,
                    "_skip": skip,
                    "_fields": "id,name,emails,phones",
                },
            )
            batch = result.get("data", [])
            contacts.extend(batch)
            if not result.get("has_more", False):
                break
            skip += limit

        return contacts

    def find_lead_by_name(self, company_name: str) -> Optional[dict[str, Any]]:
        """
        Search for an existing lead by display name to avoid duplicate creation.

        Uses the Advanced Filtering API with an exact phrase match on display_name.
        """
        if self.dry_run:
            for lead in self._dry_run_leads:
                if lead.get("name") == company_name or lead.get("display_name") == company_name:
                    return lead
            return None

        query = {
            "query": {
                "type": "and",
                "queries": [
                    {"type": "object_type", "object_type": "lead"},
                    {
                        "type": "field_condition",
                        "field": {
                            "type": "regular_field",
                            "object_type": "lead",
                            "field_name": "display_name",
                        },
                        "condition": {
                            "type": "text",
                            "mode": "phrase",
                            "value": company_name,
                        },
                    },
                ],
            },
            "_fields": {"lead": ["id", "name", "display_name", "addresses", "custom", "description"]},
            "results_limit": 1,
        }

        try:
            result = self._request("POST", "data/search/", json=query)
        except CloseAPIError:
            # Fallback: scan first page of leads (slower, but works if search is restricted).
            logger.warning("Advanced search failed for '%s'; falling back to list.", company_name)
            return self._find_lead_by_name_list(company_name)

        data = result.get("data") or []
        if not data:
            return None

        lead_id = data[0].get("id")
        if not lead_id:
            return None
        return self.get_lead(lead_id)

    def _find_lead_by_name_list(self, company_name: str) -> Optional[dict[str, Any]]:
        """Linear scan of leads when advanced search is unavailable."""
        params = {
            "_limit": 100,
            "_fields": "id,name,display_name,addresses,custom,description",
        }
        result = self._request("GET", "lead/", params=params)
        for lead in result.get("data", []):
            if lead.get("name") == company_name or lead.get("display_name") == company_name:
                return lead
        return None

    def get_lead(self, lead_id: str) -> dict[str, Any]:
        """Fetch a single lead by ID."""
        return self._request(
            "GET",
            f"lead/{lead_id}/",
            params={"_fields": "id,name,display_name,addresses,custom,description"},
        )

    def search_leads(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """
        Find leads whose founded date falls within [start_date, end_date] (inclusive).

        Uses a custom-field date range filter when CLOSE_CF_FOUNDED_DATE is set;
        otherwise fetches leads and filters client-side using description metadata.
        """
        if self.dry_run:
            return [
                lead
                for lead in self._dry_run_leads
                if (founded := extract_founded_date(lead))
                and start_date <= founded <= end_date
            ]

        if config.CLOSE_CF_FOUNDED_DATE:
            return self._search_leads_by_custom_field(start_date, end_date)

        logger.info(
            "CLOSE_CF_FOUNDED_DATE not set; listing leads and filtering by description."
        )
        return self._search_leads_client_filter(start_date, end_date)

    def _search_leads_by_custom_field(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Advanced Filtering API query on the founded-date custom field."""
        cf_key = config.CLOSE_CF_FOUNDED_DATE
        query = {
            "query": {
                "type": "and",
                "queries": [
                    {"type": "object_type", "object_type": "lead"},
                    {
                        "type": "field_condition",
                        "field": {
                            "type": "custom_field",
                            "custom_field_id": cf_key,
                        },
                        "condition": {
                            "type": "date_range",
                            "gte": start_date,
                            "lte": end_date,
                        },
                    },
                ],
            },
            "_fields": {
                "lead": [
                    "id",
                    "name",
                    "display_name",
                    "addresses",
                    "custom",
                    "description",
                ]
            },
        }
        return self._paginate_search(query)

    def _search_leads_client_filter(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """List leads and filter by founded_date parsed from description/custom."""
        matched: list[dict[str, Any]] = []
        skip = 0
        limit = 100

        while True:
            result = self._request(
                "GET",
                "lead/",
                params={
                    "_limit": limit,
                    "_skip": skip,
                    "_fields": "id,name,display_name,addresses,custom,description",
                },
            )
            batch = result.get("data", [])
            if not batch:
                break

            for lead in batch:
                founded = extract_founded_date(lead)
                if founded and start_date <= founded <= end_date:
                    matched.append(lead)

            if not result.get("has_more", False):
                break
            skip += limit

        return matched

    def _paginate_search(self, query_body: dict[str, Any]) -> list[dict[str, Any]]:
        """Page through Advanced Filtering results until cursor is null."""
        leads: list[dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            body = dict(query_body)
            body["_limit"] = 100
            if cursor:
                body["cursor"] = cursor

            result = self._request("POST", "data/search/", json=body)
            for item in result.get("data", []):
                if item.get("__object_type") == "lead" or item.get("id", "").startswith("lead_"):
                    # Search may return partial objects; hydrate when needed.
                    if "addresses" in item:
                        leads.append(item)
                    elif item.get("id"):
                        leads.append(self.get_lead(item["id"]))

            cursor = result.get("cursor")
            if not cursor:
                break

        return leads


# ---------------------------------------------------------------------------
# Lead field extraction helpers (used by search + reporting)
# ---------------------------------------------------------------------------


def extract_state(lead: dict[str, Any]) -> Optional[str]:
    """Read US state as full name (e.g. California) from description or address."""
    desc_state = _parse_description_field(lead.get("description") or "", "state", cast=str)
    if desc_state:
        return to_full_name(desc_state)

    for address in lead.get("addresses") or []:
        state = address.get("state")
        if state:
            return to_full_name(str(state).strip())
    return None


def extract_revenue(lead: dict[str, Any]) -> Optional[float]:
    """Read revenue from custom field or description fallback."""
    if config.CLOSE_CF_REVENUE:
        custom = lead.get("custom") or {}
        value = custom.get(config.CLOSE_CF_REVENUE)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass

    return _parse_description_field(lead.get("description") or "", "revenue", cast=float)


def extract_founded_date(lead: dict[str, Any]) -> Optional[str]:
    """Read founded date from custom field or description fallback."""
    if config.CLOSE_CF_FOUNDED_DATE:
        custom = lead.get("custom") or {}
        value = custom.get(config.CLOSE_CF_FOUNDED_DATE)
        if value:
            return str(value)[:10]

    return _parse_description_field(lead.get("description") or "", "founded_date", cast=str)


def build_lead_description(
    *,
    founded_date: Optional[str] = None,
    revenue: Optional[float] = None,
    state: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> str:
    """Build semicolon-separated description used for search/report fallbacks."""
    parts: list[str] = []
    if batch_id:
        parts.append(f"batch={batch_id}")
    if founded_date:
        parts.append(f"founded_date={founded_date}")
    if revenue is not None:
        parts.append(f"revenue={revenue}")
    if state:
        parts.append(f"state={state}")
    return ";".join(parts)


def extract_batch_id(lead: dict[str, Any]) -> Optional[str]:
    """Read import batch tag from lead description."""
    return _parse_description_field(lead.get("description") or "", "batch", cast=str)


def _parse_description_field(description: str, key: str, cast: type) -> Any:
    """
    Parse semicolon-separated key=value pairs from lead description.

    Example: "founded_date=2015-01-01;revenue=500000;state=CA"
    """
    for part in description.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        if k.strip() != key:
            continue
        try:
            return cast(v.strip())
        except (TypeError, ValueError):
            return None
    return None
