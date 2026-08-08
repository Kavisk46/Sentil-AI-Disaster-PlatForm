"""Datetime helpers."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return a timezone-aware current UTC timestamp.

    Centralized so every timestamped response (e.g. `/health`) is
    timezone-aware and UTC by construction, rather than each call site
    choosing between `datetime.now()`, `datetime.utcnow()` (naive, and
    deprecated as of Python 3.12), or `datetime.now(UTC)` independently.
    """
    return datetime.now(UTC)
