import json
import random
from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pytest
from app.analytics.customers.rfm import read_rfm, read_rfm_scores, rfm_score, rfm_segment
from app.analytics.shared.metrics import (
    METRICS,
    RFM_MIN_CUSTOMERS,
    RFM_NOTE,
    RFM_SCORE_FORMULA,
    RFM_SEGMENTS,
)
from app.api.customers import _rfm_body
from app.api.module_common import resolve_periods
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL

END = date(2026, 3, 31)
SEGMENT_NAMES = [
    "Champions",
    "Loyal",
    "Potential Loyalists",
    "Needs Attention",
    "At Risk",
    "Lost",
]


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


def line(order_id, day, price, customer_id, quantity=1):
    return (order_id, day, "p", "P", quantity, price, customer_id)


def customer(customer_id, last_day, orders, total):
    """``orders`` one-unit orders; the last on ``last_day``, the others one day apart before."""
    each = Decimal(total) / orders
    return [
        line(f"{customer_id}-{index}", last_day - timedelta(days=index), str(each), customer_id)
        for index in range(orders)
    ]


GOLDEN_ROWS = [
    *customer("P", date(2026, 3, 31), 5, "500.00"),
    *customer("Q", date(2026, 3, 21), 3, "300.00"),
    *customer("R", date(2026, 3, 1), 2, "300.00"),
    *customer("S", date(2026, 1, 30), 1, "50.00"),
    *customer("T", date(2025, 12, 31), 1, "20.00"),
]


def scores(rows, end=END):
    connection = connection_with_rows(rows)
    try:
        return read_rfm_scores(connection, end)
    finally:
        connection.close()


def rfm(rows, end=END):
    connection = connection_with_rows(rows)
    try:
        return read_rfm(connection, end)
    finally:
        connection.close()


def body(rows, start, end, comparison="previous_period", first="2025-01-01", last="2026-03-31"):
    connection = connection_with_rows(rows)
    try:
        periods = resolve_periods(
            start, end, comparison, date.fromisoformat(first), date.fromisoformat(last)
        )
        return _rfm_body(connection, periods)
    finally:
        connection.close()


def test_golden_example_scores_and_segments_are_exact():
    result = scores(GOLDEN_ROWS)

    assert [
        (s["recency_days"], s["frequency"], s["monetary"], s["r"], s["f"], s["m"], s["segment"])
        for s in result
    ] == [
        (0, 5, Decimal("500.00"), 5, 5, 5, "Champions"),
        (10, 3, Decimal("300.00"), 4, 4, 4, "Champions"),
        (30, 2, Decimal("300.00"), 3, 3, 4, "Loyal"),
        (60, 1, Decimal("50.00"), 2, 2, 2, "Lost"),
        (90, 1, Decimal("20.00"), 1, 2, 1, "Lost"),
    ]
    assert rfm(GOLDEN_ROWS) == {
        "customer_count": 5,
        "segment_counts": {
            "Champions": 2,
            "Loyal": 1,
            "Potential Loyalists": 0,
            "Needs Attention": 0,
            "At Risk": 0,
            "Lost": 2,
        },
    }


def test_golden_section_has_all_six_segments_with_shares():
    result = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")

    assert result == {
        "availability": {"state": "available", "reason": None},
        "customer_count": 5,
        "recency_anchor": "2026-03-31",
        "note": RFM_NOTE,
        "segments": [
            {"segment": "Champions", "customer_count": 2, "share": 0.4},
            {"segment": "Loyal", "customer_count": 1, "share": 0.2},
            {"segment": "Potential Loyalists", "customer_count": 0, "share": 0},
            {"segment": "Needs Attention", "customer_count": 0, "share": 0},
            {"segment": "At Risk", "customer_count": 0, "share": 0},
            {"segment": "Lost", "customer_count": 2, "share": 0.4},
        ],
    }


def test_range_start_has_no_effect_and_activity_after_the_end_is_ignored():
    later = [
        *GOLDEN_ROWS,
        line("late-t", date(2026, 4, 2), "1000.00", "T"),
        line("late-new", date(2026, 4, 3), "5.00", "NEW"),
    ]
    whole = body(later, "2025-12-01", "2026-03-31", last="2026-04-03")
    one_day = body(later, "2026-03-31", "2026-03-31", last="2026-04-03")

    assert whole == one_day == body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")
    assert rfm(later) == rfm(GOLDEN_ROWS)


def test_recency_is_measured_to_the_range_end():
    # P's orders are all after 2026-03-21, so P is not in the population.
    result = scores(GOLDEN_ROWS, end=date(2026, 3, 21))

    assert [(s["recency_days"], s["frequency"], s["monetary"]) for s in result] == [
        (0, 3, Decimal("300.00")),
        (20, 2, Decimal("300.00")),
        (50, 1, Decimal("50.00")),
        (80, 1, Decimal("20.00")),
    ]


def test_scores_do_not_depend_on_ids_or_row_order():
    renamed = {"P": "zz-9", "Q": "aa-1", "R": "mm-5", "S": "00", "T": "Z"}
    shuffled = [
        (f"x-{order_id}", day, product, name, quantity, price, renamed[customer_id])
        for order_id, day, product, name, quantity, price, customer_id in GOLDEN_ROWS
    ]
    random.Random(7).shuffle(shuffled)

    assert scores(shuffled) == scores(GOLDEN_ROWS)
    assert scores(list(reversed(GOLDEN_ROWS))) == scores(GOLDEN_ROWS)


def test_equal_values_get_equal_scores_and_constant_dimensions_score_three():
    rows = [line(f"o{index}", date(2026, 3, 1), "10.00", f"C{index}") for index in range(7)]
    result = scores(rows)

    assert len(result) == 7
    assert {(s["r"], s["f"], s["m"], s["segment"]) for s in result} == {(3, 3, 3, "Loyal")}


@pytest.mark.parametrize("n", range(1, 12))
def test_score_formula_is_integer_and_always_one_to_five(n):
    for worse in range(n):
        for ties in range(1, n - worse + 1):
            score = rfm_score(worse, ties, n)
            assert 1 <= score <= 5
            assert score == (5 * (2 * worse + ties)) // (2 * n) + 1
    assert rfm_score(0, n, n) == 3


def test_score_formula_examples_and_invalid_inputs():
    assert [rfm_score(worse, 1, 5) for worse in range(5)] == [1, 2, 3, 4, 5]
    assert rfm_score(0, 2, 5) == 2
    assert rfm_score(2, 2, 5) == 4
    with pytest.raises(ValueError):
        rfm_score(0, 0, 5)
    with pytest.raises(ValueError):
        rfm_score(4, 2, 5)


def expected_segment(r, f, m):
    """The segment table of issue #120, written out independently."""
    fm = f + m
    if r >= 4 and fm >= 8:
        return "Champions"
    if r >= 3 and fm >= 6:
        return "Loyal"
    if r >= 4 and fm <= 5:
        return "Potential Loyalists"
    if r == 3 and fm <= 5:
        return "Needs Attention"
    if r <= 2 and fm >= 6:
        return "At Risk"
    if r <= 2 and fm <= 5:
        return "Lost"
    raise AssertionError((r, f, m))


def test_all_125_score_combinations_get_exactly_the_table_segment():
    seen = set()
    for r in range(1, 6):
        for f in range(1, 6):
            for m in range(1, 6):
                segment = rfm_segment(r, f, m)
                assert isinstance(segment, str)
                assert segment == expected_segment(r, f, m), (r, f, m)
                seen.add(segment)
    assert seen == set(SEGMENT_NAMES)
    with pytest.raises(ValueError):
        rfm_segment(0, 3, 3)


def test_segment_table_minimum_and_note_are_shared_constants_used_by_the_registry():
    assert [segment.name for segment in RFM_SEGMENTS] == SEGMENT_NAMES
    assert all(segment.rule and segment.explanation for segment in RFM_SEGMENTS)
    assert RFM_MIN_CUSTOMERS == 5
    metric = METRICS["rfm"]
    assert metric.unit == "count"
    assert RFM_SCORE_FORMULA in metric.formula
    for segment in RFM_SEGMENTS:
        assert segment.name in metric.formula
        assert segment.rule in metric.formula
        assert segment.explanation in metric.formula
    assert str(RFM_MIN_CUSTOMERS) in metric.insufficient_data
    assert RFM_NOTE in metric.insufficient_data
    assert RFM_NOTE in metric.time_window
    assert metric.denominator


@pytest.mark.parametrize("n", [0, 4])
def test_fewer_than_five_customers_is_insufficient_data(n):
    rows = [line(f"o{index}", date(2026, 3, index + 1), "10.00", f"C{index}") for index in range(n)]
    rows.append(line("u1", date(2026, 3, 1), "10.00", None))
    result = body(rows, "2026-03-01", "2026-03-31")

    assert result == {
        "availability": {
            "state": "insufficient_data",
            "reason": "RFM needs at least 5 identified customers.",
        },
        "customer_count": n,
        "recency_anchor": "2026-03-31",
        "note": RFM_NOTE,
        "segments": [],
    }


def test_five_customers_are_available():
    rows = [line(f"o{index}", date(2026, 3, index + 1), "10.00", f"C{index}") for index in range(5)]
    result = body(rows, "2026-03-01", "2026-03-31")

    assert result["availability"] == {"state": "available", "reason": None}
    assert result["customer_count"] == 5
    assert [segment["segment"] for segment in result["segments"]] == SEGMENT_NAMES
    assert sum(segment["customer_count"] for segment in result["segments"]) == 5


def test_customers_first_ordering_after_the_end_do_not_exist():
    rows = [*GOLDEN_ROWS, line("x1", date(2026, 3, 31), "10.00", "X")]
    result = body(rows, "2026-03-01", "2026-03-30")

    assert result["customer_count"] == 5
    assert result["recency_anchor"] == "2026-03-30"


def test_unidentified_orders_do_not_change_the_result():
    with_unidentified = [
        *GOLDEN_ROWS,
        line("u1", date(2026, 3, 31), "9999.00", None),
        line("u2", date(2025, 12, 1), "1.00", None),
    ]

    assert scores(with_unidentified) == scores(GOLDEN_ROWS)
    assert body(with_unidentified, "2026-03-01", "2026-03-31") == body(
        GOLDEN_ROWS, "2026-03-01", "2026-03-31"
    )


def test_section_ignores_comparison_mode_and_is_byte_identical():
    previous = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")
    yoy = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31", comparison="previous_year")

    assert json.dumps(previous) == json.dumps(yoy)
    assert json.dumps(previous) == json.dumps(body(GOLDEN_ROWS, "2026-03-01", "2026-03-31"))
    serialized = json.dumps(previous)
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in serialized
    for customer_id in ("P", "Q", "R", "S", "T"):
        assert f'"{customer_id}"' not in serialized
