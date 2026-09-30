from datetime import date, timedelta
from decimal import Decimal

import duckdb

DAILY_MAX_DAYS = 90
WEEKLY_MAX_DAYS = 730

_ZERO_MONEY = Decimal("0.0000")
_DAILY_SQL = """
SELECT order_date, sum(quantity * unit_price)
FROM line_items
WHERE order_date BETWEEN ? AND ?
GROUP BY order_date
"""


def choose_granularity(start: date, end: date) -> str:
    """``daily`` up to 90 days, ``weekly`` up to 730, else ``monthly``.

    The span counts both ends: one date to itself is 1 day.
    """
    days = (end - start).days + 1
    if days <= DAILY_MAX_DAYS:
        return "daily"
    if days <= WEEKLY_MAX_DAYS:
        return "weekly"
    return "monthly"


def _bucket_start(day: date, granularity: str) -> date:
    if granularity == "daily":
        return day
    if granularity == "weekly":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _next_bucket(bucket: date, granularity: str) -> date:
    if granularity == "daily":
        return bucket + timedelta(days=1)
    if granularity == "weekly":
        return bucket + timedelta(days=7)
    if bucket.month == 12:
        return date(bucket.year + 1, 1, 1)
    return date(bucket.year, bucket.month + 1, 1)


def read_trend(connection: duckdb.DuckDBPyConnection, start: date, end: date) -> dict:
    """Gross sales per time bucket for rows dated ``start`` to ``end``, both included.

    Returns ``{"granularity": str, "buckets": [{"bucket_start": date,
    "gross_sales": Decimal}, ...]}`` in ascending order. The granularity depends
    only on the range. Weekly buckets start on Monday and monthly buckets on the
    1st, so the first bucket can start before ``start``; only rows inside the
    range are summed. Buckets are contiguous, empty ones hold zero. Money stays
    ``Decimal`` end to end.
    """
    if start > end:
        raise ValueError("start must not be after end")
    granularity = choose_granularity(start, end)

    totals: dict[date, Decimal] = {}
    for order_date, amount in connection.execute(_DAILY_SQL, [start, end]).fetchall():
        key = _bucket_start(order_date, granularity)
        totals[key] = totals.get(key, _ZERO_MONEY) + Decimal(amount)

    buckets = []
    bucket = _bucket_start(start, granularity)
    while bucket <= end:
        buckets.append({"bucket_start": bucket, "gross_sales": totals.get(bucket, _ZERO_MONEY)})
        bucket = _next_bucket(bucket, granularity)

    return {"granularity": granularity, "buckets": buckets}
