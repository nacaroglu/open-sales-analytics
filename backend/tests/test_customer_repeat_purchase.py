from datetime import date

import duckdb
import pytest
from app.analytics.customers.identified import read_active_customer_population
from app.analytics.customers.repeat_purchase import read_repeat_purchase


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE line_items ("
        "order_id VARCHAR, order_date DATE, product_id VARCHAR, product_name VARCHAR, "
        "quantity INTEGER, unit_price DECIMAL(18,4), customer_id VARCHAR)"
    )
    if rows:
        connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return connection


GOLDEN_ROWS = [
    ("a1", date(2026, 1, 10), "p", "P", 1, "10.00", "A"),
    ("a2", date(2026, 1, 10), "p", "P", 1, "10.00", "A"),
    ("a3", date(2026, 2, 5), "p", "P", 1, "10.00", "A"),
    ("b1", date(2026, 2, 5), "p", "P", 1, "10.00", "B"),
    ("b2", date(2026, 2, 20), "p", "P", 1, "10.00", "B"),
    ("c1", date(2026, 2, 10), "p", "P", 1, "10.00", "C"),
    ("c2", date(2026, 3, 3), "p", "P", 1, "10.00", "C"),
    ("d1", date(2026, 1, 5), "p", "P", 1, "10.00", "D"),
    ("e1", date(2026, 2, 12), "p", "P", 1, "10.00", "E"),
    ("e1", date(2026, 2, 12), "q", "Q", 1, "10.00", "E"),
    ("u1", date(2026, 2, 12), "p", "P", 1, "10.00", None),
    ("u2", date(2026, 2, 13), "p", "P", 1, "10.00", None),
]


@pytest.mark.parametrize(
    ("start", "end", "active", "repeat"),
    [
        (date(2026, 2, 1), date(2026, 2, 28), 4, 2),
        (date(2026, 2, 1), date(2026, 2, 10), 3, 1),
        (date(2026, 2, 11), date(2026, 2, 28), 2, 1),
        (date(2026, 1, 24), date(2026, 2, 10), 3, 1),
    ],
)
def test_repeat_purchase_golden_ranges_count_orders_through_the_range_end(
    start, end, active, repeat
):
    connection = connection_with_rows(GOLDEN_ROWS)
    try:
        result = read_repeat_purchase(connection, start, end)
        population = read_active_customer_population(connection, start, end)
    finally:
        connection.close()

    assert result == {"active_customers": active, "repeat_customers": repeat}
    assert len(population) == result["active_customers"]


def test_same_day_orders_count_twice_and_lines_of_one_order_count_once():
    connection = connection_with_rows(
        [
            ("x1", date(2026, 1, 1), "p", "P", 1, "1.00", "X"),
            ("x2", date(2026, 1, 1), "p", "P", 1, "1.00", "X"),
            ("y1", date(2026, 1, 1), "p", "P", 1, "1.00", "Y"),
            ("y1", date(2026, 1, 1), "q", "Q", 1, "1.00", "Y"),
            ("y1", date(2026, 1, 1), "r", "R", 1, "1.00", "Y"),
        ]
    )
    try:
        result = read_repeat_purchase(connection, date(2026, 1, 1), date(2026, 1, 1))
    finally:
        connection.close()

    assert result == {"active_customers": 2, "repeat_customers": 1}


def test_repeat_purchase_with_no_active_customers_is_zero_over_zero():
    connection = connection_with_rows(
        [("u1", date(2026, 1, 1), "p", "P", 1, "1.00", None)]
        + [("a1", date(2026, 1, 2), "p", "P", 1, "1.00", "A")]
    )
    try:
        result = read_repeat_purchase(connection, date(2026, 1, 1), date(2026, 1, 1))
    finally:
        connection.close()

    assert result == {"active_customers": 0, "repeat_customers": 0}


def test_repeat_purchase_bounds_include_both_endpoints():
    connection = connection_with_rows(
        [
            ("a1", date(2026, 1, 1), "p", "P", 1, "1.00", "A"),
            ("a2", date(2026, 1, 3), "p", "P", 1, "1.00", "A"),
            ("a3", date(2026, 1, 4), "p", "P", 1, "1.00", "A"),
        ]
    )
    try:
        on_end = read_repeat_purchase(connection, date(2026, 1, 3), date(2026, 1, 3))
        before_end = read_repeat_purchase(connection, date(2026, 1, 1), date(2026, 1, 2))
    finally:
        connection.close()

    assert on_end == {"active_customers": 1, "repeat_customers": 1}
    assert before_end == {"active_customers": 1, "repeat_customers": 0}
