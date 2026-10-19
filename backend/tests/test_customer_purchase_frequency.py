from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pytest
from app.analytics.customers.buckets import PURCHASE_FREQUENCY_BUCKETS
from app.analytics.customers.purchase_frequency import read_purchase_frequency
from app.analytics.shared.metrics import METRICS
from app.api.customers import _purchase_frequency_body
from app.api.module_common import resolve_periods
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(LINE_ITEMS_DDL)
    connection.execute(ORDER_FACTS_DDL)
    connection.execute(CUSTOMER_FACTS_DDL)
    connection.executemany(
        "INSERT INTO line_items (order_id, order_date, product_id, product_name, quantity, unit_price, customer_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.execute(
        "INSERT INTO order_facts SELECT order_id, min(order_date), max(order_date), count(*), "
        "sum(quantity), sum(quantity * unit_price) FROM line_items GROUP BY order_id"
    )
    connection.execute(
        "INSERT INTO customer_facts SELECT customer_id, min(order_date), "
        "CAST(date_trunc('month', min(order_date)) AS DATE), 1, max(order_date), "
        "count(DISTINCT order_id), sum(quantity), sum(quantity * unit_price) "
        "FROM line_items WHERE customer_id IS NOT NULL GROUP BY customer_id"
    )
    return connection


def customer_rows(customer_id: str, order_count: int, start: date = date(2025, 1, 1)):
    return [
        (f"{customer_id}-{index}", start + timedelta(days=index), "p", "Product", 1, "1.00", customer_id)
        for index in range(order_count)
    ]


def test_purchase_frequency_matches_the_golden_distribution_and_ignores_range_start():
    rows = [
        *customer_rows("C1", 1),
        *customer_rows("C2", 1),
        *customer_rows("C3", 2),
        *customer_rows("C4", 3),
        *customer_rows("C5", 7),
        *customer_rows("C6", 12),
        *customer_rows("C7", 25),
        # This later order is outside the first reporting end date.
        ("C1-later", date(2025, 2, 1), "p", "Product", 1, "1.00", "C1"),
    ]
    connection = connection_with_rows(rows)
    try:
        before_later = read_purchase_frequency(connection, date(2025, 1, 31))
        after_later = read_purchase_frequency(connection, date(2025, 2, 1))
    finally:
        connection.close()

    assert before_later == {
        "customer_count": 7,
        "bucket_counts": {"1": 2, "2": 1, "3": 1, "4": 0, "5": 0, "6-10": 1, "11-20": 1, "21+": 1},
    }
    assert after_later["bucket_counts"]["1"] == 1
    assert after_later["bucket_counts"]["2"] == 2


@pytest.mark.parametrize(
    ("order_count", "key"),
    [(5, "5"), (6, "6-10"), (10, "6-10"), (11, "11-20"), (20, "11-20"), (21, "21+")],
)
def test_purchase_frequency_bucket_edges(order_count, key):
    connection = connection_with_rows(customer_rows("C", order_count))
    try:
        result = read_purchase_frequency(connection, date(2025, 1, 31))
    finally:
        connection.close()
    assert result["bucket_counts"][key] == 1
    assert sum(result["bucket_counts"].values()) == 1


def test_purchase_frequency_api_body_has_fixed_buckets_shares_and_no_comparison():
    rows = [*customer_rows("C1", 1), *customer_rows("C2", 2)]
    connection = connection_with_rows(rows)
    try:
        periods = resolve_periods(
            "2025-01-01", "2025-01-31", "previous_year", date(2025, 1, 1), date(2025, 2, 1)
        )
        body = _purchase_frequency_body(connection, periods)
    finally:
        connection.close()

    assert body["availability"] == {"state": "available", "reason": None}
    assert body["customer_count"] == 2
    assert body["single_order_share"] == 0.5
    assert [bucket["key"] for bucket in body["buckets"]] == [bucket.key for bucket in PURCHASE_FREQUENCY_BUCKETS]
    assert body["buckets"][0]["share"] == 0.5
    assert body["buckets"][1]["share"] == 0.5
    assert all("comparison" not in bucket for bucket in body["buckets"])


def test_purchase_frequency_empty_population_is_insufficient_and_keeps_eight_buckets():
    connection = connection_with_rows(
        [("o1", date(2025, 1, 3), "p", "Product", 1, "0.00", "C1")]
    )
    try:
        periods = resolve_periods(
            "2025-01-02", "2025-01-02", "previous_period", date(2025, 1, 1), date(2025, 1, 3)
        )
        body = _purchase_frequency_body(connection, periods)
    finally:
        connection.close()

    assert body["availability"]["state"] == "insufficient_data"
    assert body["customer_count"] == 0
    assert body["single_order_share"] is None
    assert len(body["buckets"]) == 8
    assert all(bucket["customer_count"] == 0 and bucket["share"] is None for bucket in body["buckets"])


def test_purchase_frequency_metric_definition_is_complete():
    metric = METRICS["purchase_frequency"]
    assert metric.unit == "count"
    assert metric.numerator and metric.denominator and metric.time_window and metric.insufficient_data
    assert "6-10" in metric.formula
    assert "range start has no effect" in metric.time_window


def test_purchase_frequency_uses_bound_dates_and_no_customer_rows_escape():
    connection = connection_with_rows(customer_rows("MARKER", 1))
    try:
        result = read_purchase_frequency(connection, date(2025, 1, 31))
    finally:
        connection.close()
    assert result["customer_count"] == 1
    assert "MARKER" not in repr(result)
    assert Decimal("1") == Decimal(result["bucket_counts"]["1"])
