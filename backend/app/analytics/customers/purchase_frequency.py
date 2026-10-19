"""Distribution of identified customers by distinct orders through a range end."""

from datetime import date
from typing import TypedDict

import duckdb

from app.analytics.customers.buckets import PURCHASE_FREQUENCY_BUCKETS


class PurchaseFrequencyBucket(TypedDict):
    key: str
    min_orders: int
    max_orders: int | None
    customer_count: int


class PurchaseFrequencyResult(TypedDict):
    customer_count: int
    bucket_counts: dict[str, int]


def read_purchase_frequency(
    connection: duckdb.DuckDBPyConnection, end: date
) -> PurchaseFrequencyResult:
    """Count identified customers by distinct order count through ``end``.

    The query returns only aggregate bucket counts. Customer identifiers and individual
    customer order counts never leave DuckDB.
    """
    rows = connection.execute(
        """
        WITH customer_orders AS (
            SELECT li.customer_id, count(DISTINCT li.order_id) AS order_count
            FROM line_items AS li
            JOIN customer_facts AS cf ON cf.customer_id = li.customer_id
            WHERE li.customer_id IS NOT NULL
              AND li.order_date <= ?
              AND cf.first_order_date <= ?
            GROUP BY li.customer_id
        ), bucketed AS (
            SELECT CASE
                WHEN order_count = 1 THEN '1'
                WHEN order_count = 2 THEN '2'
                WHEN order_count = 3 THEN '3'
                WHEN order_count = 4 THEN '4'
                WHEN order_count = 5 THEN '5'
                WHEN order_count BETWEEN 6 AND 10 THEN '6-10'
                WHEN order_count BETWEEN 11 AND 20 THEN '11-20'
                ELSE '21+'
            END AS bucket
            FROM customer_orders
        )
        SELECT bucket, count(*)
        FROM bucketed
        GROUP BY bucket
        """,
        [end, end],
    ).fetchall()
    counts = {bucket.key: 0 for bucket in PURCHASE_FREQUENCY_BUCKETS}
    for key, count in rows:
        counts[str(key)] = int(count)
    return {
        "customer_count": sum(counts.values()),
        "bucket_counts": counts,
    }
