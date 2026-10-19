"""Top-decile concentration of identified customer gross sales."""

from datetime import date
from decimal import Decimal
from typing import TypedDict

import duckdb


class ConcentrationResult(TypedDict):
    customer_count: int
    top_decile_customer_count: int
    top_decile_gross_sales: Decimal
    identified_gross_sales: Decimal


def read_concentration(
    connection: duckdb.DuckDBPyConnection, start: date, end: date
) -> ConcentrationResult:
    """Aggregate customer sales and rank them without returning customer rows.

    The active population is formed by identified customers with activity in the
    inclusive range.  ``ROW_NUMBER`` is only used to select the k largest values;
    ties at the boundary therefore need no customer-specific tie-break.
    """
    row = connection.execute(
        """
        WITH customer_sales AS (
            SELECT customer_id, SUM(quantity * unit_price) AS gross_sales
            FROM line_items
            WHERE customer_id IS NOT NULL
              AND order_date BETWEEN ? AND ?
            GROUP BY customer_id
        ), ranked AS (
            SELECT gross_sales,
                   COUNT(*) OVER () AS customer_count,
                   CEIL(COUNT(*) OVER () / 10.0) AS top_decile_customer_count,
                   ROW_NUMBER() OVER (ORDER BY gross_sales DESC) AS sales_rank
            FROM customer_sales
        )
        SELECT
            COALESCE(MAX(customer_count), 0),
            COALESCE(MAX(top_decile_customer_count), 0),
            COALESCE(SUM(gross_sales) FILTER (WHERE sales_rank <= top_decile_customer_count), 0),
            COALESCE(SUM(gross_sales), 0)
        FROM ranked
        """,
        [start, end],
    ).fetchone()
    assert row is not None
    customer_count, top_count, top_sales, total_sales = row
    return {
        "customer_count": int(customer_count),
        "top_decile_customer_count": int(top_count),
        "top_decile_gross_sales": Decimal(top_sales),
        "identified_gross_sales": Decimal(total_sales),
    }
