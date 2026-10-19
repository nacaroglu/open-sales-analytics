from datetime import date

import duckdb
from app.analytics.customers.identified import (
    read_active_customer_population,
    read_identified_customer_count,
)


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE line_items (order_id VARCHAR, order_date DATE, customer_id VARCHAR)"
    )
    connection.executemany("INSERT INTO line_items VALUES (?, ?, ?)", rows)
    return connection


def test_identified_customers_counts_distinct_active_non_blank_customers_once():
    connection = connection_with_rows(
        [
            ("o1", date(2026, 2, 28), "c1"),
            ("o2", date(2026, 3, 1), "c1"),
            ("o3", date(2026, 3, 15), "c2"),
            ("o4", date(2026, 3, 15), "c2"),
            ("o5", date(2026, 3, 31), None),
            ("o6", date(2026, 4, 1), "c3"),
        ]
    )
    try:
        assert read_active_customer_population(connection, date(2026, 3, 1), date(2026, 3, 31)) == [
            "c1",
            "c2",
        ]
        assert read_identified_customer_count(connection, date(2026, 3, 1), date(2026, 3, 31)) == 2
        assert read_identified_customer_count(connection, date(2026, 2, 28), date(2026, 2, 28)) == 1
        assert read_identified_customer_count(connection, date(2026, 3, 2), date(2026, 3, 14)) == 0
    finally:
        connection.close()


def test_identified_customer_population_uses_bound_date_parameters():
    connection = connection_with_rows([("o1", date(2026, 3, 1), "marker")])
    try:
        assert read_identified_customer_count(connection, date(2026, 3, 1), date(2026, 3, 1)) == 1
    finally:
        connection.close()
