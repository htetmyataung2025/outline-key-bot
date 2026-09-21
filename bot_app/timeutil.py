"""Shared time helper: single source for Myanmar time (UTC+6:30)."""

from datetime import datetime, timedelta, timezone

_MYANMAR_OFFSET = timedelta(hours=6, minutes=30)


def myanmar_now() -> datetime:
    """Timezone-naive Myanmar local time (keeps existing storage formats)."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + _MYANMAR_OFFSET


def myanmar_today():
    return myanmar_now().date()


def format_myanmar_now(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return myanmar_now().strftime(fmt)
