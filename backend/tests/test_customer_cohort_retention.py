from datetime import date

import duckdb
import pytest
from app.analytics.customers.cohort_retention import cell_state, cohort_grid, read_cohort_retention
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL


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


def line(order_id, day, customer_id):
    return (order_id, day, "p", "P", 1, "10.00", customer_id)


GOLDEN_ROWS = [
    line("a1", date(2026, 1, 10), "A"),
    line("a2", date(2026, 2, 5), "A"),
    line("a3", date(2026, 3, 7), "A"),
    line("f1", date(2026, 1, 20), "F"),
    line("b1", date(2026, 2, 5), "B"),
    line("g1", date(2026, 2, 25), "G"),
    line("g2", date(2026, 3, 20), "G"),
    line("h1", date(2026, 3, 3), "H"),
    line("u1", date(2026, 3, 31), None),
]


def read(rows, start, end):
    connection = connection_with_rows(rows)
    try:
        return read_cohort_retention(connection, start, end)
    finally:
        connection.close()


def cells(*specs):
    return [
        {"month_offset": offset, "state": state, "retained_count": count}
        for offset, (state, count) in enumerate(specs)
    ]


NOT_OBSERVED = ("not_observed", None)
JANUARY = {
    "cohort_month": date(2026, 1, 1),
    "cohort_size": 2,
    "cells": cells(("complete", 2), ("complete", 1), ("partial", 1)),
}
FEBRUARY = {
    "cohort_month": date(2026, 2, 1),
    "cohort_size": 2,
    "cells": cells(("complete", 2), ("partial", 0), NOT_OBSERVED),
}
MARCH = {
    "cohort_month": date(2026, 3, 1),
    "cohort_size": 1,
    "cells": cells(("partial", 1), NOT_OBSERVED, NOT_OBSERVED),
}


def test_golden_range_has_three_rectangular_rows_with_maturity_states():
    assert read(GOLDEN_ROWS, date(2026, 1, 10), date(2026, 3, 15)) == [JANUARY, FEBRUARY, MARCH]


def test_mid_month_start_keeps_customers_acquired_before_it_in_their_cohort():
    assert read(GOLDEN_ROWS, date(2026, 1, 15), date(2026, 3, 15)) == [JANUARY, FEBRUARY, MARCH]


def test_start_selects_rows_and_does_not_change_them():
    february = {**FEBRUARY, "cells": FEBRUARY["cells"][:2]}
    march = {**MARCH, "cells": MARCH["cells"][:2]}
    # Rectangular to the oldest returned cohort: February spans two months to the cutoff.
    assert read(GOLDEN_ROWS, date(2026, 2, 1), date(2026, 3, 15)) == [february, march]


def test_month_end_cutoff_completes_march_and_ignores_unidentified_orders():
    rows = read(GOLDEN_ROWS, date(2026, 1, 10), date(2026, 3, 31))
    assert rows == [
        {**JANUARY, "cells": cells(("complete", 2), ("complete", 1), ("complete", 1))},
        {**FEBRUARY, "cells": cells(("complete", 2), ("complete", 1), NOT_OBSERVED)},
        {**MARCH, "cells": cells(("complete", 1), NOT_OBSERVED, NOT_OBSERVED)},
    ]
    without_unidentified = read(GOLDEN_ROWS[:-1], date(2026, 1, 10), date(2026, 3, 31))
    assert without_unidentified == rows


def test_customers_first_seen_after_the_range_end_are_not_members():
    rows = read(GOLDEN_ROWS, date(2026, 1, 10), date(2026, 2, 10))
    assert [(row["cohort_month"], row["cohort_size"]) for row in rows] == [
        (date(2026, 1, 1), 2),
        (date(2026, 2, 1), 1),
    ]
    assert rows[1]["cells"] == cells(("partial", 1), NOT_OBSERVED)


def test_year_boundary_month_one_is_january():
    rows = [
        line("x1", date(2025, 12, 30), "X"),
        line("x2", date(2026, 1, 2), "X"),
        line("y1", date(2025, 12, 31), "Y"),
    ]
    assert read(rows, date(2025, 12, 1), date(2026, 1, 31)) == [
        {
            "cohort_month": date(2025, 12, 1),
            "cohort_size": 2,
            "cells": cells(("complete", 2), ("complete", 1)),
        }
    ]


def test_no_overlapping_cohort_returns_no_rows():
    assert read(GOLDEN_ROWS, date(2026, 4, 1), date(2026, 5, 31)) == []
    assert read([line("u1", date(2026, 1, 1), None)], date(2026, 1, 1), date(2026, 1, 31)) == []


def test_repeat_lines_in_one_month_count_a_customer_once():
    rows = [
        line("a1", date(2026, 1, 1), "A"),
        line("a2", date(2026, 1, 1), "A"),
        line("a3", date(2026, 1, 5), "A"),
    ]
    assert read(rows, date(2026, 1, 1), date(2026, 1, 31))[0]["cells"] == cells(("complete", 1))


@pytest.mark.parametrize(
    ("month", "cutoff", "state"),
    [
        (date(2026, 2, 1), date(2026, 2, 28), "complete"),
        (date(2026, 2, 1), date(2026, 2, 27), "partial"),
        (date(2026, 2, 1), date(2026, 2, 1), "partial"),
        (date(2026, 2, 1), date(2026, 1, 31), "not_observed"),
        (date(2024, 2, 1), date(2024, 2, 29), "complete"),
        (date(2025, 12, 1), date(2025, 12, 31), "complete"),
    ],
)
def test_cell_state_compares_the_calendar_month_with_the_cutoff(month, cutoff, state):
    assert cell_state(month, cutoff) == state


def test_cohort_grid_selects_overlapping_months_oldest_first_and_pads_rows():
    months = [date(2026, 3, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 4, 1)]
    grid = cohort_grid(months, date(2026, 1, 20), date(2026, 3, 15))
    assert [month for month, _ in grid] == [date(2026, 1, 1), date(2026, 3, 1)]
    assert grid[0][1] == [(0, "complete"), (1, "complete"), (2, "partial")]
    assert grid[1][1] == [(0, "partial"), (1, "not_observed"), (2, "not_observed")]
    assert cohort_grid([], date(2026, 1, 1), date(2026, 1, 31)) == []
