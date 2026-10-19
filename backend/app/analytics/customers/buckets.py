"""Fixed day buckets for the days-between-purchases distribution."""

from typing import NamedTuple


class DayBucket(NamedTuple):
    """An inclusive range of interval lengths in days; ``max_days`` ``None`` is open."""

    key: str
    min_days: int
    max_days: int | None


DAYS_BETWEEN_PURCHASES_BUCKETS: tuple[DayBucket, ...] = (
    DayBucket("0", 0, 0),
    DayBucket("1-7", 1, 7),
    DayBucket("8-14", 8, 14),
    DayBucket("15-30", 15, 30),
    DayBucket("31-60", 31, 60),
    DayBucket("61-90", 61, 90),
    DayBucket("91-180", 91, 180),
    DayBucket("181-365", 181, 365),
    DayBucket("366+", 366, None),
)


def bucket_key(days: int) -> str:
    """Return the key of the bucket that contains an interval of ``days``."""
    for bucket in DAYS_BETWEEN_PURCHASES_BUCKETS:
        if days >= bucket.min_days and (bucket.max_days is None or days <= bucket.max_days):
            return bucket.key
    raise ValueError(f"interval must be non-negative, got {days}")
