"""Repeat-purchase rate for the active identified-customer population."""

from datetime import date

import duckdb

from app.analytics.customers.identified import read_active_customer_population


def read_repeat_purchase(
    connection: duckdb.DuckDBPyConnection, start: date, end: date
) -> dict[str, int]:
    """Count active customers and those with two or more orders by ``end``.

    The population is #114's active-customer population for the range. Orders are
    counted from the start of the upload through ``end`` (orders before ``start``
    count, orders after ``end`` do not), so full-upload ``customer_facts`` totals are
    not used. Customer IDs stay inside this function and are passed to SQL only as a
    bound list parameter.
    """
    population = read_active_customer_population(connection, start, end)
    if not population:
        return {"active_customers": 0, "repeat_customers": 0}
    row = connection.execute(
        """
        SELECT count(*)
        FROM (
            SELECT customer_id
            FROM line_items
            WHERE customer_id IN (SELECT unnest(CAST(? AS VARCHAR[])))
              AND order_date <= ?
            GROUP BY customer_id
            HAVING count(DISTINCT order_id) >= 2
        )
        """,
        [population, end],
    ).fetchone()
    assert row is not None
    return {"active_customers": len(population), "repeat_customers": int(row[0])}
