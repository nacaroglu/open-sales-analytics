from datetime import date
from decimal import Decimal

import duckdb
import pytest
from app.analytics.customers.cohort_retention import read_cohort_retention
from app.analytics.customers.historical_value import (
    read_cumulative_value_by_cohort_age,
    read_historical_customer_value,
)
from app.api.customers import _historical_customer_value_body
from app.api.module_common import resolve_periods
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL

FIRST, LAST = "2026-01-10", "2026-03-31"


def connection_with_rows(rows):
    """Build line_items, order_facts and customer_facts (full history) in memory."""
    connection = duckdb.connect(":memory:")
    connection.execute(LINE_ITEMS_DDL)
    connection.execute(ORDER_FACTS_DDL)
    connection.execute(CUSTOMER_FACTS_DDL)
    connection.executemany(
        "INSERT INTO line_items (order_id, order_date, product_id, product_name, "
        "quantity, unit_price, customer_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.execute(
        "INSERT INTO order_facts SELECT order_id, min(order_date), max(order_date), "
        "count(*), sum(quantity), sum(quantity * unit_price) FROM line_items GROUP BY order_id"
    )
    connection.execute(
        """
        INSERT INTO customer_facts
        SELECT customer_id, min(order_date), CAST(date_trunc('month', min(order_date)) AS DATE),
               1, max(order_date), count(DISTINCT order_id), sum(quantity),
               sum(quantity * unit_price)
        FROM line_items WHERE customer_id IS NOT NULL GROUP BY customer_id
        """
    )
    return connection


def line(order_id, day, price, customer_id):
    return (order_id, day, "p", "P", 1, price, customer_id)


GOLDEN_ROWS = [
    line("a1", date(2026, 1, 10), "100.00", "A"),
    line("a2", date(2026, 2, 5), "30.00", "A"),
    line("f1", date(2026, 1, 20), "50.00", "F"),
    line("b1", date(2026, 2, 5), "20.00", "B"),
    line("b2", date(2026, 3, 10), "40.00", "B"),
    line("u1", date(2026, 2, 15), "999.00", None),
    line("u2", date(2026, 3, 31), "1.00", None),
]


def body(rows, start, end, first=FIRST, last=LAST):
    connection = connection_with_rows(rows)
    try:
        periods = resolve_periods(
            start, end, "previous_period", date.fromisoformat(first), date.fromisoformat(last)
        )
        return _historical_customer_value_body(connection, periods)
    finally:
        connection.close()


def cell(offset, state, value):
    return {"month_offset": offset, "state": state, "value_per_customer": value}


def point(offset, value, cohorts):
    return {"month_offset": offset, "value_per_customer": value, "contributing_cohorts": cohorts}


def test_golden_full_range_has_average_median_cells_and_curve():
    result = body(GOLDEN_ROWS, "2026-01-10", "2026-03-31")

    assert result == {
        "availability": {"state": "available", "reason": None},
        "data_cutoff": "2026-03-31",
        "customer_count": 3,
        "average": "80.0000",
        "median": "60.0000",
        "rows": [
            {
                "cohort_month": "2026-01",
                "cohort_size": 2,
                "cells": [
                    cell(0, "complete", "75.0000"),
                    cell(1, "complete", "90.0000"),
                    cell(2, "complete", "90.0000"),
                ],
            },
            {
                "cohort_month": "2026-02",
                "cohort_size": 1,
                "cells": [
                    cell(0, "complete", "20.0000"),
                    cell(1, "complete", "60.0000"),
                    cell(2, "not_observed", None),
                ],
            },
        ],
        "all_cohorts": [point(0, "56.6667", 2), point(1, "80.0000", 2), point(2, "90.0000", 1)],
    }


def test_golden_mid_month_cutoff_has_partial_cells_excluded_from_the_curve():
    result = body(GOLDEN_ROWS, "2026-01-10", "2026-03-15")

    assert result["data_cutoff"] == "2026-03-15"
    january, february = result["rows"]
    assert january["cells"][2] == cell(2, "partial", "90.0000")
    assert february["cells"][1] == cell(1, "partial", "60.0000")
    assert february["cells"][2] == cell(2, "not_observed", None)
    assert result["all_cohorts"] == [
        point(0, "56.6667", 2),
        point(1, "90.0000", 1),
        point(2, None, 0),
    ]


def test_golden_later_start_keeps_only_the_february_cohort():
    result = body(GOLDEN_ROWS, "2026-02-01", "2026-03-31")

    assert [row["cohort_month"] for row in result["rows"]] == ["2026-02"]
    assert (result["customer_count"], result["average"], result["median"]) == (
        1,
        "60.0000",
        "60.0000",
    )


def test_golden_even_count_median_is_the_mean_of_the_two_middle_values():
    result = body(GOLDEN_ROWS, "2026-01-10", "2026-01-31")

    assert (result["customer_count"], result["average"], result["median"]) == (
        2,
        "75.0000",
        "75.0000",
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-01-10", "2026-03-31"),
        ("2026-01-10", "2026-03-15"),
        ("2026-02-01", "2026-03-31"),
        ("2026-01-10", "2026-01-31"),
    ],
)
def test_unidentified_orders_change_no_number(start, end):
    identified = [row for row in GOLDEN_ROWS if row[-1] is not None]
    without = body(identified, start, end)
    with_unidentified = body(GOLDEN_ROWS, start, end)

    assert without == with_unidentified


def test_rows_and_states_match_cohort_retention():
    connection = connection_with_rows(GOLDEN_ROWS)
    try:
        for cutoff in (date(2026, 1, 31), date(2026, 3, 15), date(2026, 3, 31)):
            retention = read_cohort_retention(connection, date(2026, 1, 10), cutoff)
            value = read_cumulative_value_by_cohort_age(connection, date(2026, 1, 10), cutoff)
            assert [
                (row["cohort_month"], row["cohort_size"], [c["state"] for c in row["cells"]])
                for row in value
            ] == [
                (row["cohort_month"], row["cohort_size"], [c["state"] for c in row["cells"]])
                for row in retention
            ]
    finally:
        connection.close()


def test_reader_returns_decimal_cumulative_sales_and_counts_lines_before_the_start():
    connection = connection_with_rows(GOLDEN_ROWS)
    try:
        rows = read_cumulative_value_by_cohort_age(connection, date(2026, 1, 15), date(2026, 3, 15))
        summary = read_historical_customer_value(connection, date(2026, 1, 15), date(2026, 3, 15))
    finally:
        connection.close()

    assert rows[0]["cells"][0]["cumulative_gross_sales"] == Decimal("150.00")
    assert isinstance(rows[0]["cells"][0]["cumulative_gross_sales"], Decimal)
    assert rows[1]["cells"][2]["cumulative_gross_sales"] is None
    assert summary["customer_count"] == 3
    assert summary["total_value"] == Decimal("240.00")
    assert summary["median"] == Decimal("60.00")


def test_customers_acquired_after_the_cutoff_do_not_exist_for_the_request():
    result = body(GOLDEN_ROWS, "2026-01-10", "2026-02-04")

    # B (first order 2026-02-05) is not a member; A's 2026-02-05 line is after the cutoff.
    assert result["customer_count"] == 2
    assert result["average"] == "75.0000"
    assert [row["cohort_month"] for row in result["rows"]] == ["2026-01"]


def test_empty_population_is_insufficient_data():
    result = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")

    assert result["availability"]["state"] == "insufficient_data"
    assert result["availability"]["reason"]
    assert (result["customer_count"], result["average"], result["median"]) == (0, None, None)
    assert result["rows"] == []
    assert result["all_cohorts"] == []


def test_zero_price_customer_counts_with_zero_value():
    rows = [*GOLDEN_ROWS, line("z1", date(2026, 1, 25), "0.00", "Z")]
    result = body(rows, "2026-01-10", "2026-03-31")

    assert result["customer_count"] == 4
    assert result["average"] == "60.0000"
    assert result["median"] == "55.0000"
    assert result["rows"][0]["cohort_size"] == 3
    assert result["rows"][0]["cells"][0] == cell(0, "complete", "50.0000")


def test_population_with_zero_total_is_zero_result_with_numbers():
    rows = [line("z1", date(2026, 1, 10), "0.00", "Z"), line("u1", date(2026, 3, 31), "5.00", None)]
    result = body(rows, "2026-01-10", "2026-03-31")

    assert result["availability"]["state"] == "zero_result"
    assert result["availability"]["reason"]
    assert (result["customer_count"], result["average"], result["median"]) == (
        1,
        "0.0000",
        "0.0000",
    )
    assert result["rows"][0]["cells"][0] == cell(0, "complete", "0.0000")
    assert result["all_cohorts"][0] == point(0, "0.0000", 1)


def test_money_rounds_half_up_from_exact_values():
    rows = [
        line("a1", date(2026, 1, 10), "0.0001", "A"),
        line("b1", date(2026, 1, 11), "0.0000", "B"),
        line("u1", date(2026, 1, 31), "1.00", None),
    ]
    result = body(rows, "2026-01-10", "2026-01-31", last="2026-01-31")

    # 0.0001 / 2 = 0.00005: half-up gives 0.0001 where half-even would give 0.0000.
    assert result["average"] == "0.0001"
    assert result["median"] == "0.0001"
    assert result["rows"][0]["cells"][0]["value_per_customer"] == "0.0001"
