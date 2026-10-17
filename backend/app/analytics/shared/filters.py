"""Shared parsing for analytics request filters."""

import re
from datetime import date

_DATE_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_day(name: str, text: str) -> date:
    """Parse a strict ISO calendar date, preserving public API error messages."""
    if not _DATE_FORM.fullmatch(text):
        raise ValueError(f"{name} must be a date written YYYY-MM-DD.")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{name} is not a real date.") from None
