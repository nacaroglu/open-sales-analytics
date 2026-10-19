from datetime import date, timedelta

import duckdb
import pytest
from app.analytics.customers.buckets import DAYS_BETWEEN_PURCHASES_BUCKETS, bucket_key
from app.analytics.customers.days_between_purchases import read_days_between_purchases
from app.schema import LINE_ITEMS_DDL, ORDER_FACTS_DDL

KEYS = ["0", "1-7", "8-14", "15-30", "31-60", "61-90", "91-180", "181-365", "366+"]


def connection_with_rows(rows):
    """Build line_items and order_facts (dated by each order's first line) in memory."""
    connection = duckdb.connect(":memory:")
    connection.execute(LINE_ITEMS_DDL)
    connection.execute(ORDER_FACTS_DDL)
    if rows:
        connection.executemany(
            "INSERT INTO line_items (order_id, order_date, product_id, product_name, "
            "quantity, unit_price, customer_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    connection.execute(
        "INSERT INTO order_facts SELECT order_id, min(order_date), max(order_date), "
        "count(*), sum(quantity), sum(quantity * unit_price) FROM line_items GROUP BY order_id"
    )
    return connection


def line(order_id, day, customer_id):
    return (order_id, day, "p", "P", 1, "10.00", customer_id)


GOLDEN_ROWS = [
    line("a1", date(2026, 1, 10), "A"),
    line("a2", date(2026, 1, 10), "A"),
    line("a3", date(2026, 2, 5), "A"),
    line("a4", date(2026, 3, 7), "A"),
    line("b1", date(2026, 2, 5), "B"),
    line("b2", date(2026, 2, 20), "B"),
    line("c1", date(2026, 2, 10), "C"),
    line("u1", date(2026, 2, 12), None),
]


def read(rows, start, end):
    connection = connection_with_rows(rows)
    try:
        return read_days_between_purchases(connection, start, end)
    finally:
        connection.close()


def counts(**nonzero):
    return {key: nonzero.get(key, 0) for key in KEYS}


def test_bucket_constants_are_the_nine_fixed_inclusive_buckets():
    assert [tuple(bucket) for bucket in DAYS_BETWEEN_PURCHASES_BUCKETS] == [
        ("0", 0, 0),
        ("1-7", 1, 7),
        ("8-14", 8, 14),
        ("15-30", 15, 30),
        ("31-60", 31, 60),
        ("61-90", 61, 90),
        ("91-180", 91, 180),
        ("181-365", 181, 365),
        ("366+", 366, None),
    ]


def test_golden_full_range_has_four_intervals_and_an_even_count_median():
    result = read(GOLDEN_ROWS, date(2026, 1, 10), date(2026, 3, 7))

    assert result == {
        "median_days": 20.5,
        "interval_count": 4,
        "contributing_customers": 2,
        "bucket_counts": counts(**{"0": 1, "15-30": 3}),
    }


def test_golden_interval_whose_earlier_order_is_before_the_range_is_included():
    result = read(GOLDEN_ROWS, date(2026, 3, 1), date(2026, 3, 7))

    assert result == {
        "median_days": 30,
        "interval_count": 1,
        "contributing_customers": 1,
        "bucket_counts": counts(**{"15-30": 1}),
    }


def test_golden_same_day_orders_give_a_zero_interval_and_later_orders_are_ignored():
    result = read(GOLDEN_ROWS, date(2026, 1, 10), date(2026, 1, 31))

    assert result == {
        "median_days": 0,
        "interval_count": 1,
        "contributing_customers": 1,
        "bucket_counts": counts(**{"0": 1}),
    }


def test_leap_day_interval_counts_calendar_days():
    rows = [line("x1", date(2024, 2, 28), "X"), line("x2", date(2024, 3, 1), "X")]

    result = read(rows, date(2024, 2, 28), date(2024, 3, 1))

    assert result["median_days"] == 2
    assert result["bucket_counts"] == counts(**{"1-7": 1})


@pytest.mark.parametrize(
    ("days", "key"),
    [
        (0, "0"),
        (1, "1-7"),
        (7, "1-7"),
        (8, "8-14"),
        (14, "8-14"),
        (15, "15-30"),
        (30, "15-30"),
        (31, "31-60"),
        (60, "31-60"),
        (61, "61-90"),
        (90, "61-90"),
        (91, "91-180"),
        (180, "91-180"),
        (181, "181-365"),
        (365, "181-365"),
        (366, "366+"),
    ],
)
def test_bucket_edges_are_inclusive(days, key):
    first = date(2024, 1, 1)
    rows = [line("x1", first, "X"), line("x2", first + timedelta(days=days), "X")]

    result = read(rows, first, first + timedelta(days=days))

    assert bucket_key(days) == key
    assert result["interval_count"] == 1
    assert result["median_days"] == days
    assert result["bucket_counts"] == counts(**{key: 1})


def test_lines_of_one_order_are_one_order_and_an_order_is_dated_by_its_first_line():
    rows = [
        line("x1", date(2026, 1, 1), "X"),
        line("x2", date(2026, 1, 5), "X"),
        line("x2", date(2026, 1, 20), "X"),
        line("x2", date(2026, 1, 25), "X"),
    ]

    inside = read(rows, date(2026, 1, 1), date(2026, 1, 31))
    later_lines_only = read(rows, date(2026, 1, 10), date(2026, 1, 31))

    assert inside["interval_count"] == 1
    assert inside["median_days"] == 4
    assert later_lines_only["interval_count"] == 0


def test_same_day_order_ids_do_not_change_results():
    forward = [
        line("a", date(2026, 1, 1), "X"),
        line("b", date(2026, 1, 3), "X"),
        line("c", date(2026, 1, 3), "X"),
        line("d", date(2026, 1, 10), "X"),
    ]
    renamed = [
        line("d", date(2026, 1, 1), "X"),
        line("c", date(2026, 1, 3), "X"),
        line("b", date(2026, 1, 3), "X"),
        line("a", date(2026, 1, 10), "X"),
    ]

    assert read(forward, date(2026, 1, 1), date(2026, 1, 10)) == read(
        renamed, date(2026, 1, 1), date(2026, 1, 10)
    )
    assert read(forward, date(2026, 1, 1), date(2026, 1, 10))["bucket_counts"] == counts(
        **{"0": 1, "1-7": 2}
    )


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [line("u1", date(2026, 1, 1), None), line("u2", date(2026, 1, 2), None)],
        [line("x1", date(2026, 1, 1), "X"), line("y1", date(2026, 1, 2), "Y")],
    ],
)
def test_no_included_interval_returns_empty_aggregates(rows):
    result = read(rows, date(2026, 1, 1), date(2026, 1, 31))

    assert result == {
        "median_days": None,
        "interval_count": 0,
        "contributing_customers": 0,
        "bucket_counts": counts(),
    }


def test_range_without_repeat_orders_and_both_endpoints_are_included():
    rows = [
        line("x1", date(2026, 1, 1), "X"),
        line("x2", date(2026, 1, 3), "X"),
        line("x3", date(2026, 1, 9), "X"),
    ]

    assert read(rows, date(2026, 1, 4), date(2026, 1, 8))["interval_count"] == 0
    on_start = read(rows, date(2026, 1, 3), date(2026, 1, 3))
    on_end = read(rows, date(2026, 1, 4), date(2026, 1, 9))
    assert (on_start["interval_count"], on_start["median_days"]) == (1, 2)
    assert (on_end["interval_count"], on_end["median_days"]) == (1, 6)
