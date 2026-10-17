"""Aggregate customer coverage for the Customers module."""

from datetime import date

import duckdb

from app.analytics.shared.availability import CustomerCoverage


def read_customer_coverage(
    connection: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
) -> CustomerCoverage:
    """Return order-level coverage without selecting or exposing customer IDs."""
    predicates: list[str] = []
    parameters: list[date] = []
    if start is not None:
        predicates.append("order_date >= ?")
        parameters.append(start)
    if end is not None:
        predicates.append("order_date <= ?")
        parameters.append(end)
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    has_customer_id = connection.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = 'line_items' AND column_name = 'customer_id'"
    ).fetchone()
    assert has_customer_id is not None
    if not has_customer_id[0]:
        row = connection.execute(
            "SELECT count(DISTINCT order_id) FROM line_items" + where,
            parameters,
        ).fetchone()
        assert row is not None
        total_orders = int(row[0])
        return CustomerCoverage(0, total_orders, total_orders)
    row = connection.execute(
        "SELECT count(*) AS total_orders, "
        "count(*) FILTER (WHERE identified) AS identified_orders "
        "FROM (SELECT order_id, bool_or(customer_id IS NOT NULL) AS identified "
        f"FROM line_items{where} GROUP BY order_id)",
        parameters,
    ).fetchone()
    assert row is not None
    total_orders, identified_orders = int(row[0]), int(row[1])
    return CustomerCoverage(identified_orders, total_orders - identified_orders, total_orders)
