"""Fixed buckets shared by the customer distributions.

- ``DAYS_BETWEEN_PURCHASES_BUCKETS``: interval lengths for days between purchases.
- ``RFM_RECENCY_BUCKETS``: RFM recency (days since the latest order) for the drill-downs.
- ``PURCHASE_FREQUENCY_BUCKETS``: distinct orders per customer; defined once here and
  shared by the RFM drill-downs and the purchase-frequency distribution.

All ranges are inclusive; the last bucket of each tuple is open (its maximum is ``None``).
"""

from typing import NamedTuple


class DayBucket(NamedTuple):
    """An inclusive range of interval lengths in days; ``max_days`` ``None`` is open."""

    key: str
    min_days: int
    max_days: int | None


class OrderBucket(NamedTuple):
    """An inclusive range of distinct-order counts; ``max_orders`` ``None`` is open."""

    key: str
    min_orders: int
    max_orders: int | None


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

RFM_RECENCY_BUCKETS: tuple[DayBucket, ...] = (
    DayBucket("0-30", 0, 30),
    DayBucket("31-60", 31, 60),
    DayBucket("61-90", 61, 90),
    DayBucket("91-180", 91, 180),
    DayBucket("181-365", 181, 365),
    DayBucket("366+", 366, None),
)

PURCHASE_FREQUENCY_BUCKETS: tuple[OrderBucket, ...] = (
    OrderBucket("1", 1, 1),
    OrderBucket("2", 2, 2),
    OrderBucket("3", 3, 3),
    OrderBucket("4", 4, 4),
    OrderBucket("5", 5, 5),
    OrderBucket("6-10", 6, 10),
    OrderBucket("11-20", 11, 20),
    OrderBucket("21+", 21, None),
)


def _find(buckets: tuple[tuple[str, int, int | None], ...], value: int) -> str | None:
    for key, low, high in buckets:
        if value >= low and (high is None or value <= high):
            return key
    return None


def bucket_key(days: int) -> str:
    """Return the key of the bucket that contains an interval of ``days``."""
    key = _find(DAYS_BETWEEN_PURCHASES_BUCKETS, days)
    if key is None:
        raise ValueError(f"interval must be non-negative, got {days}")
    return key


def recency_bucket_key(days: int) -> str:
    """Return the key of the RFM recency bucket that contains ``days``."""
    key = _find(RFM_RECENCY_BUCKETS, days)
    if key is None:
        raise ValueError(f"recency must be non-negative, got {days}")
    return key


def frequency_bucket_key(orders: int) -> str:
    """Return the key of the purchase-frequency bucket that contains ``orders``."""
    key = _find(PURCHASE_FREQUENCY_BUCKETS, orders)
    if key is None:
        raise ValueError(f"frequency must be at least 1, got {orders}")
    return key
