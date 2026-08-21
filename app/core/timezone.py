"""IST (India Standard Time) helpers.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Return the current time as a timezone-aware IST datetime."""
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    """Convert a datetime to IST. Naive datetimes are assumed to be UTC (matches
    User.created_at, which is stored via datetime.utcnow)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)
