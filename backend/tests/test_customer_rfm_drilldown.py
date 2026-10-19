import json
from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pytest
from app.analytics.customers.buckets import (
    PURCHASE_FREQUENCY_BUCKETS,
    RFM_RECENCY_BUCKETS,
    DayBucket,
    OrderBucket,
    frequency_bucket_key,
    recency_bucket_key,
)
from app.analytics.customers.rfm import read_rfm_drilldown, read_rfm_scores, rfm_drilldown
from app.analytics.shared.metrics import METRICS, RFM_MIN_CUSTOMERS, RFM_NOTE
from app.api.customers import _rfm_body, _rfm_drilldown_body
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
RECENCY_KEYS = ["0-30", "31-60", "61-90", "91-180", "181-365", "366+"]
FREQUENCY_KEYS = ["1", "2", "3", "4", "5", "6-10", "11-20", "21+"]


def connection_with_rows(rows):
    """Build line_items, order_facts and customer_facts (full history) in memory."""
    connection = duckdb.connect(":memory:")
    connection.execute(LINE_ITEMS_DDL)
    connection.execute(ORDER_FACTS_DDL)
    connection.execute(CUSTOMER_FACTS_DDL)
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


# Copied from test_customer_rfm.py (#120).
GOLDEN_ROWS = [
    *customer("P", date(2026, 3, 31), 5, "500.00"),
    *customer("Q", date(2026, 3, 21), 3, "300.00"),
    *customer("R", date(2026, 3, 1), 2, "300.00"),
    *customer("S", date(2026, 1, 30), 1, "50.00"),
    *customer("T", date(2025, 12, 31), 1, "20.00"),
]


def body(rows, start, end, comparison="previous_period", first="2025-01-01", last="2026-03-31"):
    connection = connection_with_rows(rows)
    try:
        periods = resolve_periods(
            start, end, comparison, date.fromisoformat(first), date.fromisoformat(last)
        )
        return _rfm_drilldown_body(connection, periods)
    finally:
        connection.close()


def rfm_section(rows, start, end):
    connection = connection_with_rows(rows)
    try:
        periods = resolve_periods(start, end, "previous_period", date(2025, 1, 1), END)
        return _rfm_body(connection, periods)
    finally:
        connection.close()


def counts(distribution):
    return {
        bucket["key"]: bucket["customer_count"]
        for bucket in distribution
        if bucket["customer_count"]
    }


def by_name(section):
    return {segment["segment"]: segment for segment in section["segments"]}


def test_golden_example_top_level_and_segments():
    result = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")

    assert result["availability"] == {"state": "available", "reason": None}
    assert result["customer_count"] == 5
    assert result["gross_sales"] == "1170.0000"
    assert result["recency_anchor"] == "2026-03-31"
    assert set(result) == {
        "availability",
        "customer_count",
        "recency_anchor",
        "gross_sales",
        "segments",
    }
    assert [segment["segment"] for segment in result["segments"]] == SEGMENT_NAMES
    segments = by_name(result)
    champions = segments["Champions"]
    assert (champions["customer_count"], champions["gross_sales"]) == (2, "800.0000")
    assert champions["gross_sales_share"] == 0.6838
    assert counts(champions["recency_distribution"]) == {"0-30": 2}
    assert counts(champions["frequency_distribution"]) == {"3": 1, "5": 1}
    loyal = segments["Loyal"]
    assert (loyal["customer_count"], loyal["gross_sales"], loyal["gross_sales_share"]) == (
        1,
        "300.0000",
        0.2564,
    )
    assert counts(loyal["recency_distribution"]) == {"0-30": 1}
    assert counts(loyal["frequency_distribution"]) == {"2": 1}
    lost = segments["Lost"]
    assert (lost["customer_count"], lost["gross_sales"], lost["gross_sales_share"]) == (
        2,
        "70.0000",
        0.0598,
    )
    assert counts(lost["recency_distribution"]) == {"31-60": 1, "61-90": 1}
    assert counts(lost["frequency_distribution"]) == {"1": 2}
    for name in ("Potential Loyalists", "Needs Attention", "At Risk"):
        segment = segments[name]
        assert (segment["customer_count"], segment["gross_sales"]) == (0, "0.0000")
        assert segment["gross_sales_share"] == 0
        assert counts(segment["recency_distribution"]) == {}
        assert counts(segment["frequency_distribution"]) == {}


def test_buckets_carry_keys_edges_and_fixed_order():
    segment = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")["segments"][0]

    assert segment["recency_distribution"][0] == {
        "key": "0-30",
        "min_days": 0,
        "max_days": 30,
        "customer_count": 2,
    }
    assert segment["recency_distribution"][-1] == {
        "key": "366+",
        "min_days": 366,
        "max_days": None,
        "customer_count": 0,
    }
    assert [bucket["key"] for bucket in segment["recency_distribution"]] == RECENCY_KEYS
    assert segment["frequency_distribution"][5] == {
        "key": "6-10",
        "min_orders": 6,
        "max_orders": 10,
        "customer_count": 0,
    }
    assert segment["frequency_distribution"][-1]["max_orders"] is None
    assert [bucket["key"] for bucket in segment["frequency_distribution"]] == FREQUENCY_KEYS


def test_bucket_constants_reuse_the_shared_tuple_types():
    assert all(isinstance(bucket, DayBucket) for bucket in RFM_RECENCY_BUCKETS)
    assert all(isinstance(bucket, OrderBucket) for bucket in PURCHASE_FREQUENCY_BUCKETS)
    assert [bucket.key for bucket in RFM_RECENCY_BUCKETS] == RECENCY_KEYS
    assert [bucket.key for bucket in PURCHASE_FREQUENCY_BUCKETS] == FREQUENCY_KEYS
    assert OrderBucket._fields == ("key", "min_orders", "max_orders")


@pytest.mark.parametrize(
    ("days", "key"),
    [
        (0, "0-30"),
        (30, "0-30"),
        (31, "31-60"),
        (60, "31-60"),
        (61, "61-90"),
        (90, "61-90"),
        (91, "91-180"),
        (180, "91-180"),
        (181, "181-365"),
        (365, "181-365"),
        (366, "366+"),
        (5000, "366+"),
    ],
)
def test_recency_bucket_edges(days, key):
    assert recency_bucket_key(days) == key


@pytest.mark.parametrize(
    ("orders", "key"),
    [
        (1, "1"),
        (2, "2"),
        (3, "3"),
        (4, "4"),
        (5, "5"),
        (6, "6-10"),
        (10, "6-10"),
        (11, "11-20"),
        (20, "11-20"),
        (21, "21+"),
        (900, "21+"),
    ],
)
def test_frequency_bucket_edges(orders, key):
    assert frequency_bucket_key(orders) == key


def test_bucket_helpers_reject_out_of_range_values():
    with pytest.raises(ValueError):
        recency_bucket_key(-1)
    with pytest.raises(ValueError):
        frequency_bucket_key(0)


def test_drilldown_uses_the_same_population_and_segments_as_rfm():
    section = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")
    rfm = rfm_section(GOLDEN_ROWS, "2026-03-01", "2026-03-31")

    assert section["customer_count"] == rfm["customer_count"]
    assert section["recency_anchor"] == rfm["recency_anchor"]
    assert [(s["segment"], s["customer_count"]) for s in section["segments"]] == [
        (s["segment"], s["customer_count"]) for s in rfm["segments"]
    ]
    connection = connection_with_rows(GOLDEN_ROWS)
    try:
        assert read_rfm_drilldown(connection, END) == rfm_drilldown(
            read_rfm_scores(connection, END)
        )
    finally:
        connection.close()


@pytest.mark.parametrize("n", [0, 4])
def test_fewer_than_five_customers_is_insufficient_data_with_real_totals(n):
    rows = [line(f"o{index}", date(2026, 3, index + 1), "10.50", f"C{index}") for index in range(n)]
    result = body(rows, "2026-03-01", "2026-03-31")

    assert result == {
        "availability": {
            "state": "insufficient_data",
            "reason": "RFM needs at least 5 identified customers.",
        },
        "customer_count": n,
        "recency_anchor": "2026-03-31",
        "gross_sales": f"{Decimal('10.50') * n:.4f}",
        "segments": [],
    }
    assert RFM_MIN_CUSTOMERS == 5


def test_five_customers_are_available():
    rows = [line(f"o{index}", date(2026, 3, index + 1), "10.00", f"C{index}") for index in range(5)]
    result = body(rows, "2026-03-01", "2026-03-31")

    assert result["availability"] == {"state": "available", "reason": None}
    assert result["customer_count"] == 5
    assert len(result["segments"]) == 6


def test_zero_total_gross_sales_gives_null_shares():
    rows = [line(f"o{index}", date(2026, 3, index + 1), "0.00", f"C{index}") for index in range(5)]
    result = body(rows, "2026-03-01", "2026-03-31")

    assert result["gross_sales"] == "0.0000"
    assert all(segment["gross_sales_share"] is None for segment in result["segments"])
    assert sum(segment["customer_count"] for segment in result["segments"]) == 5


def test_a_single_member_segment_is_returned_like_any_other():
    loyal = by_name(body(GOLDEN_ROWS, "2026-03-01", "2026-03-31"))["Loyal"]

    assert loyal["customer_count"] == 1
    assert loyal["gross_sales"] == "300.0000"


def test_forty_customers_keep_fixed_lengths_and_consistent_bucket_sums():
    rows = []
    for index in range(40):
        orders = 1 + index % 25
        last = END - timedelta(days=index * 11)
        rows += customer(f"C{index:02}", last, orders, f"{(index + 1) * 13}.37")
    result = body(rows, "2026-03-01", "2026-03-31", first="2024-01-01")

    assert result["availability"]["state"] == "available"
    assert result["customer_count"] == 40
    assert len(result["segments"]) == 6
    total = Decimal(0)
    for segment in result["segments"]:
        assert len(segment["recency_distribution"]) == 6
        assert len(segment["frequency_distribution"]) == 8
        for distribution in ("recency_distribution", "frequency_distribution"):
            assert (
                sum(bucket["customer_count"] for bucket in segment[distribution])
                == segment["customer_count"]
            )
        total += Decimal(segment["gross_sales"])
    assert sum(segment["customer_count"] for segment in result["segments"]) == 40
    assert total == Decimal(result["gross_sales"])


def test_range_start_and_comparison_mode_have_no_effect_and_output_is_byte_identical():
    previous = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31")
    yoy = body(GOLDEN_ROWS, "2026-03-01", "2026-03-31", comparison="previous_year")
    one_day = body(GOLDEN_ROWS, "2026-03-31", "2026-03-31")
    whole = body(GOLDEN_ROWS, "2025-12-01", "2026-03-31")

    assert json.dumps(previous) == json.dumps(yoy) == json.dumps(one_day) == json.dumps(whole)
    assert json.dumps(previous) == json.dumps(body(GOLDEN_ROWS, "2026-03-01", "2026-03-31"))
    serialized = json.dumps(previous)
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in serialized
    for customer_id in ("P", "Q", "R", "S", "T"):
        assert f'"{customer_id}"' not in serialized


def test_unidentified_orders_do_not_change_the_result():
    with_unidentified = [
        *GOLDEN_ROWS,
        line("u1", date(2026, 3, 31), "9999.00", None),
        line("u2", date(2025, 12, 1), "1.00", None),
    ]

    assert body(with_unidentified, "2026-03-01", "2026-03-31") == body(
        GOLDEN_ROWS, "2026-03-01", "2026-03-31"
    )


def test_customers_first_ordering_after_the_end_do_not_exist():
    rows = [*GOLDEN_ROWS, line("x1", date(2026, 3, 31), "10.00", "X")]
    result = body(rows, "2026-03-01", "2026-03-30")

    assert result["customer_count"] == 5
    assert result["recency_anchor"] == "2026-03-30"
    assert result == body(GOLDEN_ROWS, "2026-03-01", "2026-03-30")


def test_activity_after_the_end_is_ignored():
    later = [*GOLDEN_ROWS, line("late-t", date(2026, 4, 2), "1000.00", "T")]

    assert body(later, "2026-03-01", "2026-03-31", last="2026-04-02") == body(
        GOLDEN_ROWS, "2026-03-01", "2026-03-31"
    )


def test_metric_registry_entry_documents_the_drilldown():
    metric = METRICS["rfm_drilldown"]

    assert metric.unit == "count"
    assert metric.denominator
    for key in RECENCY_KEYS + ["6-10", "11-20", "21+"]:
        assert key in metric.formula
    assert "gross_sales_share" in metric.formula
    assert str(RFM_MIN_CUSTOMERS) in metric.insufficient_data
    assert RFM_NOTE in metric.insufficient_data
    assert RFM_NOTE in metric.time_window
