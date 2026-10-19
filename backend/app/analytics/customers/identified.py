"""Aggregate identified-customer analytics for the Customers module."""

from datetime import date

import duckdb


def read_active_customer_population(
    connection: duckdb.DuckDBPyConnection, start: date, end: date
) -> list[str]:
    """Return opaque IDs with activity in the inclusive range.

    IDs stay inside the analytics layer and are never serialized or logged.
    """
    rows = connection.execute(
        """
        SELECT DISTINCT customer_id
        FROM line_items
        WHERE order_date >= ? AND order_date <= ? AND customer_id IS NOT NULL
        ORDER BY customer_id
        """,
        [start, end],
    ).fetchall()
    return [str(row[0]) for row in rows]


def read_identified_customer_count(
    connection: duckdb.DuckDBPyConnection, start: date, end: date
) -> int:
    """Count the active identified-customer population without exposing IDs."""
    return len(read_active_customer_population(connection, start, end))
