"""
Parse messy take-home CSV field values into normalized Python types.

The MOCK_DATA file uses European dates, currency strings, and multi-value contact fields.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# European date: D.M.YYYY or DD.MM.YYYY (day and month may be 1-2 digits).
EU_DATE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$"
)

# Practical email check for import (reject obvious typos from the mock file).
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

# Split emails on comma, semicolon, or newline.
EMAIL_SPLIT_PATTERN = re.compile(r"[,;\n]+")

# Strip non-phone decoration (emoji, labels like "unknown").
PHONE_CLEANUP_PATTERN = re.compile(r"[^\d+\-().\s]")


def parse_founded_date(raw: str) -> Optional[str]:
    """
    Parse custom.Company Founded values into ISO YYYY-MM-DD for Close API storage.

    Examples: 17.05.1987, 15.3.1976, 8.6.1987, 23.3.1967
    """
    if not raw or not str(raw).strip():
        return None

    text = str(raw).strip()
    match = EU_DATE_PATTERN.match(text)
    if not match:
        return None

    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_revenue(raw: str) -> Optional[float]:
    """
    Parse custom.Company Revenue into a float.

    Examples: $1231970.94, "$2,777,611.57", $7657374.19
    """
    if raw is None or not str(raw).strip():
        return None

    cleaned = str(raw).strip().replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None

    try:
        value = float(cleaned)
    except ValueError:
        return None

    return value if value >= 0 else None


def split_emails(raw: str) -> list[str]:
    """Split and trim email field; empty tokens are removed."""
    if not raw or not str(raw).strip():
        return []
    return [part.strip() for part in EMAIL_SPLIT_PATTERN.split(str(raw)) if part.strip()]


def is_valid_email(email: str) -> bool:
    """Return True when an email is well-formed enough to import."""
    email = email.strip()
    if not email or "??" in email:
        return False
    return bool(EMAIL_PATTERN.match(email))


def parse_valid_emails(raw: str) -> list[str]:
    """Return all valid emails from a possibly multi-valued cell."""
    return [e for e in split_emails(raw) if is_valid_email(e)]


def split_phones(raw: str) -> list[str]:
    """Split phone field on newlines; strip noise from each entry."""
    if not raw or not str(raw).strip():
        return []

    phones: list[str] = []
    for line in str(raw).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower() == "unknown":
            continue
        # Remove emoji / letters (e.g. 📞) but keep + and digits.
        cleaned = PHONE_CLEANUP_PATTERN.sub("", line).strip()
        if cleaned:
            phones.append(cleaned)
    return phones


def is_valid_phone(phone: str) -> bool:
    """Phone is usable when it contains enough digits (mock data has short junk like +123)."""
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 7


def parse_valid_phones(raw: str) -> list[str]:
    """Return phones that meet minimum digit length."""
    return [p for p in split_phones(raw) if is_valid_phone(p)]


def normalize_email_key(email: str) -> str:
    """Canonical email for duplicate detection."""
    return email.strip().lower()


def normalize_phone_key(phone: str) -> str:
    """Digits-only phone for duplicate detection."""
    return re.sub(r"\D", "", phone)


def format_currency(amount: float) -> str:
    """Format like sample output: $15,325,123.00"""
    return f"${amount:,.2f}"
