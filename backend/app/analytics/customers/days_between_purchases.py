"""Median and bucketed distribution of days between a customer's consecutive orders."""

from datetime import date
from typing import TypedDict

import duckdb

from app.analytics.customers.buckets import DAYS_BETWEEN_PURCHASES_BUCKETS, bucket_key


class DaysBetweenPurchases(TypedDict):
    median_days: float | None
    interval_count: int
    contributing_customers: int
    bucket_counts: dict[str, int]


def read_days_between_purchases(
    connection: duckdb.DuckDBPyConnection, start: date, end: date
) -> DaysBetweenPurchases:
    """Aggregate the intervals between consecutive identified orders.

    An order is dated by ``order_facts.first_order_date``. Each customer's distinct
    identified orders dated on or before ``end`` are sorted by that date; an interval
    is included when its later order is dated inside ``[start, end]`` (its earlier order
    may be before ``start``). Same-day orders give a ``0`` interval. Only aggregates are
    returned; customer IDs never leave the SQL.
    """
    rows = connection.execute(
        """
        WITH identified_orders AS (
            SELECT DISTINCT li.customer_id, li.order_id, facts.first_order_date AS order_date
            FROM line_items AS li
            JOIN order_facts AS facts ON facts.order_id = li.order_id
            WHERE li.customer_id IS NOT NULL AND facts.first_order_date <= ?
        ), intervals AS (
            SELECT customer_id,
                   order_date,
                   date_diff(
                       'day',
                       lag(order_date) OVER (
                           PARTITION BY customer_id ORDER BY order_date, order_id
                       ),
                       order_date
                   ) AS days
            FROM identified_orders
        ), included AS (
            SELECT customer_id, days
            FROM intervals
            WHERE days IS NOT NULL AND order_date >= ?
        )
        SELECT days, count(*) AS interval_count, NULL AS contributing_customers
        FROM included
        GROUP BY days
        UNION ALL
        SELECT NULL, NULL, count(DISTINCT customer_id)
        FROM included
        """,
        [end, start],
    ).fetchall()
    histogram = {int(row[0]): int(row[1]) for row in rows if row[0] is not None}
    contributing = next(int(row[2]) for row in rows if row[0] is None)
    bucket_counts = {bucket.key: 0 for bucket in DAYS_BETWEEN_PURCHASES_BUCKETS}
    for days, count in histogram.items():
        bucket_counts[bucket_key(days)] += count
    interval_count = sum(histogram.values())
    return {
        "median_days": _median(histogram, interval_count),
        "interval_count": interval_count,
        "contributing_customers": contributing,
        "bucket_counts": bucket_counts,
    }


def _median(histogram: dict[int, int], total: int) -> float | None:
    """Median of a histogram of integer values; the mean of the two middles when even."""
    if not total:
        return None
    lower_index, upper_index = (total - 1) // 2, total // 2
    lower = upper = None
    seen = 0
    for days in sorted(histogram):
        seen += histogram[days]
        if lower is None and seen > lower_index:
            lower = days
        if seen > upper_index:
            upper = days
            break
    assert lower is not None and upper is not None
    return (lower + upper) / 2
