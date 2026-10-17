"""Date bucketing shared by time-series analytics."""

from datetime import date, timedelta

DAILY_MAX_DAYS = 90
WEEKLY_MAX_DAYS = 730


def choose_granularity(start: date, end: date) -> str:
    """Return ``daily`` up to 90 days, ``weekly`` up to 730, else ``monthly``."""
    days = (end - start).days + 1
    if days <= DAILY_MAX_DAYS:
        return "daily"
    if days <= WEEKLY_MAX_DAYS:
        return "weekly"
    return "monthly"


def _bucket_start(day: date, granularity: str) -> date:
    """Return the inclusive bucket containing ``day``."""
    if granularity == "daily":
        return day
    if granularity == "weekly":
        return day - timedelta(days=day.weekday())
    if granularity == "monthly":
        return day.replace(day=1)
    raise ValueError(f"Unsupported granularity: {granularity}")


def _next_bucket(bucket: date, granularity: str) -> date:
    """Return the first day of the bucket after ``bucket``."""
    if granularity == "daily":
        return bucket + timedelta(days=1)
    if granularity == "weekly":
        return bucket + timedelta(days=7)
    if granularity == "monthly":
        if bucket.month == 12:
            return date(bucket.year + 1, 1, 1)
        return date(bucket.year, bucket.month + 1, 1)
    raise ValueError(f"Unsupported granularity: {granularity}")
