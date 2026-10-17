from datetime import date
from decimal import Decimal

import duckdb

from app.analytics.shared.buckets import _bucket_start, _next_bucket, choose_granularity

_ZERO_MONEY = Decimal("0.0000")
_DAILY_SQL = """
SELECT order_date, sum(quantity * unit_price)
FROM line_items
WHERE order_date BETWEEN ? AND ?
GROUP BY order_date
"""


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
