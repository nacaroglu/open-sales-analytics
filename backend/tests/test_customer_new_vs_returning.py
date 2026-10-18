from datetime import date
from decimal import Decimal

import duckdb
import pytest
from app.analytics.customers.new_vs_returning import read_new_vs_returning


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE line_items ("
        "order_id VARCHAR, order_date DATE, product_id VARCHAR, product_name VARCHAR, "
        "quantity INTEGER, unit_price DECIMAL(18,4), customer_id VARCHAR)"
    )
    connection.execute("CREATE TABLE customer_facts (customer_id VARCHAR, first_order_date DATE)")
    if rows:
        connection.executemany(
            "INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    connection.executemany(
        "INSERT INTO customer_facts VALUES (?, ?)",
        [("A", date(2026, 1, 10)), ("B", date(2026, 2, 5))],
    )
    return connection


GOLDEN_ROWS = [
    ("a1", date(2026, 1, 10), "p", "P", 1, "100.00", "A"),
    ("a2", date(2026, 1, 10), "q", "Q", 1, "50.00", "A"),
    ("a3", date(2026, 2, 5), "p", "P", 1, "30.00", "A"),
    ("b1", date(2026, 2, 5), "p", "P", 1, "20.00", "B"),
    ("b2", date(2026, 2, 20), "p", "P", 1, "40.00", "B"),
    ("u1", date(2026, 2, 10), "p", "P", 1, "999.00", None),
]


@pytest.mark.parametrize(
    ("start", "end", "new", "returning", "identified", "rows"),
    [
        (date(2026, 1, 10), date(2026, 2, 20), "170.0000", "70.0000", "240.0000", 5),
        (date(2026, 2, 1), date(2026, 2, 20), "20.0000", "70.0000", "90.0000", 3),
        (date(2026, 1, 11), date(2026, 2, 20), "20.0000", "70.0000", "90.0000", 3),
        (date(2026, 1, 10), date(2026, 1, 31), "150.0000", "0.0000", "150.0000", 2),
    ],
)
def test_new_vs_returning_golden_ranges_use_full_history(
    start, end, new, returning, identified, rows
):
    connection = connection_with_rows(GOLDEN_ROWS)
    try:
        result = read_new_vs_returning(connection, start, end)
    finally:
        connection.close()

    assert result == {
        "new_customer_gross_sales": Decimal(new),
        "returning_customer_gross_sales": Decimal(returning),
        "identified_gross_sales": Decimal(identified),
        "identified_rows": rows,
    }
    assert str(result["new_customer_gross_sales"]) == new
    assert (
        result["new_customer_gross_sales"] + result["returning_customer_gross_sales"]
        == result["identified_gross_sales"]
    )


def test_new_vs_returning_splits_an_order_with_two_line_dates():
    connection = connection_with_rows(
        [
            ("mixed", date(2026, 2, 5), "q", "Q", 1, "7.00", "B"),
            ("mixed", date(2026, 2, 6), "r", "R", 1, "8.00", "B"),
        ]
    )
    try:
        result = read_new_vs_returning(connection, date(2026, 2, 1), date(2026, 2, 28))
    finally:
        connection.close()

    assert result == {
        "new_customer_gross_sales": Decimal("7.0000"),
        "returning_customer_gross_sales": Decimal("8.0000"),
        "identified_gross_sales": Decimal("15.0000"),
        "identified_rows": 2,
    }


def test_new_vs_returning_keeps_zero_price_lines_and_excludes_unidentified_rows():
    connection = connection_with_rows(
        [
            ("a1", date(2026, 1, 10), "p", "P", 1, "0.00", "A"),
            ("u1", date(2026, 1, 10), "p", "P", 1, "999.00", None),
        ]
    )
    try:
        result = read_new_vs_returning(connection, date(2026, 1, 10), date(2026, 1, 10))
    finally:
        connection.close()

    assert result == {
        "new_customer_gross_sales": Decimal("0.0000"),
        "returning_customer_gross_sales": Decimal("0.0000"),
        "identified_gross_sales": Decimal("0.0000"),
        "identified_rows": 1,
    }


def test_new_vs_returning_empty_range_has_zero_values():
    connection = connection_with_rows([])
    try:
        result = read_new_vs_returning(connection, date(2026, 3, 1), date(2026, 3, 1))
    finally:
        connection.close()

    assert result == {
        "new_customer_gross_sales": Decimal("0.0000"),
        "returning_customer_gross_sales": Decimal("0.0000"),
        "identified_gross_sales": Decimal("0.0000"),
        "identified_rows": 0,
    }
