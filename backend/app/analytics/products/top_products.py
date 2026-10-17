from datetime import date
from decimal import Decimal

import duckdb

_TOP_PRODUCTS_SQL = """
SELECT product_id,
       min(product_name),
       sum(quantity * unit_price) AS gross_sales,
       sum(quantity),
       count(DISTINCT order_id)
FROM line_items
WHERE order_date BETWEEN ? AND ?
GROUP BY product_id
ORDER BY gross_sales DESC, product_id ASC
LIMIT ?
"""


def read_top_products(
    connection: duckdb.DuckDBPyConnection, start: date, end: date, n: int = 10
) -> list[dict]:
    """The ``n`` best-selling products by gross sales for rows dated ``start`` to ``end``.

    Returns ``[{"product_id": str, "product_name": str, "gross_sales": Decimal,
    "units_sold": int, "distinct_orders": int}, ...]``, highest gross sales
    first; ties are broken by ``product_id`` ascending, compared as text
    (``p10`` before ``p2``). Products are grouped by ``product_id``. If an id
    ever carried several names, the alphabetically smallest is reported so the
    result stays deterministic. Fewer than ``n`` products gives a shorter list.
    Money stays ``Decimal`` end to end. Raises ``ValueError`` if ``n`` < 1.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    rows = connection.execute(_TOP_PRODUCTS_SQL, [start, end, n]).fetchall()
    return [
        {
            "product_id": product_id,
            "product_name": product_name,
            "gross_sales": Decimal(gross_sales),
            "units_sold": int(units_sold),
            "distinct_orders": int(distinct_orders),
        }
        for product_id, product_name, gross_sales, units_sold, distinct_orders in rows
    ]


def read_product_count(connection: duckdb.DuckDBPyConnection, start: date, end: date) -> int:
    """Count products with at least one line item in the inclusive range."""
    row = connection.execute(
        "SELECT count(DISTINCT product_id) FROM line_items WHERE order_date BETWEEN ? AND ?",
        [start, end],
    ).fetchone()
    assert row is not None
    return int(row[0])


def read_product_identity(connection: duckdb.DuckDBPyConnection, product_id: str) -> dict | None:
    """Return the stable product identity, without interpolating the uploaded ID."""
    row = connection.execute(
        "SELECT product_id, product_name FROM product_facts WHERE product_id = ?",
        [product_id],
    ).fetchone()
    if row is None:
        return None
    return {"product_id": row[0], "product_name": row[1]}


def read_product_kpis(
    connection: duckdb.DuckDBPyConnection, product_id: str, start: date, end: date
) -> dict:
    """Return product KPI values, including zeros for a range without product sales."""
    row = connection.execute(
        """
        SELECT sum(quantity * unit_price), sum(quantity), count(DISTINCT order_id)
        FROM line_items
        WHERE product_id = ? AND order_date BETWEEN ? AND ?
        """,
        [product_id, start, end],
    ).fetchone()
    assert row is not None
    gross_sales, units_sold, orders = row
    return {
        "gross_sales": Decimal(gross_sales) if gross_sales is not None else Decimal("0.0000"),
        "units_sold": int(units_sold or 0),
        "orders": int(orders or 0),
    }


def read_product_trend(
    connection: duckdb.DuckDBPyConnection,
    product_id: str,
    start: date,
    end: date,
    granularity: str,
) -> list[dict]:
    """Return contiguous product buckets at the caller-selected granularity."""
    from app.analytics.shared.buckets import _bucket_start, _next_bucket

    rows = connection.execute(
        """
        SELECT order_date, sum(quantity * unit_price)
        FROM line_items
        WHERE product_id = ? AND order_date BETWEEN ? AND ?
        GROUP BY order_date
        """,
        [product_id, start, end],
    ).fetchall()
    totals: dict[date, Decimal] = {}
    for day, amount in rows:
        bucket = _bucket_start(day, granularity)
        totals[bucket] = totals.get(bucket, Decimal("0.0000")) + Decimal(amount)
    buckets = []
    bucket = _bucket_start(start, granularity)
    while bucket <= end:
        buckets.append(
            {"bucket_start": bucket, "gross_sales": totals.get(bucket, Decimal("0.0000"))}
        )
        bucket = _next_bucket(bucket, granularity)
    return buckets
