from datetime import date
from decimal import Decimal

import duckdb
import pytest
from app.analytics.shared.availability import (
    CustomerCoverage,
    customer_availability,
    customer_coverage,
    customer_coverage_tier,
    rounded_coverage,
)
from app.meta import read_meta


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE line_items (order_id VARCHAR, order_date DATE, customer_id VARCHAR)"
    )
    connection.executemany("INSERT INTO line_items VALUES (?, ?, ?)", rows)
    return connection


def test_coverage_counts_distinct_orders_after_customer_fill():
    connection = connection_with_rows(
        [
            ("identified", date(2025, 1, 1), "C1"),
            ("identified", date(2025, 1, 1), "C1"),
            ("identified", date(2025, 1, 1), "C1"),
            ("identified", date(2025, 1, 1), "C1"),
            ("identified", date(2025, 1, 1), "C1"),
            ("blank-a", date(2025, 1, 2), None),
            ("blank-b", date(2025, 1, 3), None),
        ]
    )
    try:
        result = customer_coverage(connection)
    finally:
        connection.close()
    assert result == CustomerCoverage(1, 2, 3)
    assert rounded_coverage(result) == Decimal("0.3333")


def test_date_range_coverage_is_inclusive_and_empty_is_null():
    connection = connection_with_rows(
        [("o1", date(2025, 1, 1), "C1"), ("o2", date(2025, 1, 3), None)]
    )
    try:
        assert customer_coverage(
            connection, date(2025, 1, 1), date(2025, 1, 1)
        ) == CustomerCoverage(1, 0, 1)
        empty = customer_coverage(connection, date(2025, 2, 1), date(2025, 2, 2))
    finally:
        connection.close()
    assert empty == CustomerCoverage(0, 0, 0)
    assert empty.coverage is None


@pytest.mark.parametrize(
    ("identified", "total", "expected"),
    [
        (4999, 10000, "suppressed"),
        (1, 2, "warning"),
        (5000, 10000, "warning"),
        (7999, 10000, "warning"),
        (4, 5, "normal"),
        (8000, 10000, "normal"),
        (1, 1, "normal"),
        (0, 10, "suppressed"),
    ],
)
def test_customer_coverage_tiers_use_exact_integer_boundaries(identified, total, expected):
    assert (
        customer_coverage_tier(True, CustomerCoverage(identified, total - identified, total))
        == expected
    )


def test_missing_customer_column_is_not_zero_percent_coverage():
    coverage = CustomerCoverage(0, 10, 10)
    assert customer_coverage_tier(False, coverage) == "missing"
    assert customer_availability(False, coverage) == {
        "state": "unavailable",
        "reason": "The file has no customer_id column.",
    }


def test_warning_availability_is_available_with_a_low_coverage_warning():
    availability = customer_availability(True, CustomerCoverage(1, 1, 2))
    assert availability["state"] == "available"
    assert availability["warning"] == {
        "state": "low_coverage",
        "reason": "Only 1 of 2 orders (50%) have a customer_id; customer results describe those orders only.",
    }


def test_suppressed_reason_rounds_down_and_has_no_identifiers():
    availability = customer_availability(True, CustomerCoverage(4999, 5001, 10000))
    assert availability["reason"] == (
        "Customer analytics needs a customer_id on at least 50% of orders; "
        "4,999 of 10,000 orders (49%) have one."
    )


def test_legacy_dataset_without_customer_metadata_reads_as_missing(tmp_path):
    path = tmp_path / "legacy.duckdb"
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE line_items (order_id VARCHAR, order_date DATE, product_id VARCHAR, "
            "product_name VARCHAR, quantity INTEGER, unit_price DECIMAL(18,4))"
        )
        connection.execute(
            "CREATE TABLE order_facts (order_id VARCHAR, first_order_date DATE, last_order_date DATE, "
            "line_count INTEGER, units BIGINT, gross_sales DECIMAL(38,4))"
        )
        connection.execute(
            "CREATE TABLE product_facts (product_id VARCHAR, product_name VARCHAR, first_sale_date DATE, "
            "last_sale_date DATE, lifetime_gross_sales DECIMAL(38,4), lifetime_units BIGINT, "
            "lifetime_orders BIGINT)"
        )
        connection.execute(
            "CREATE TABLE dataset_meta (id VARCHAR, currency VARCHAR, created_at TIMESTAMPTZ, "
            "expires_at TIMESTAMPTZ, token_hash VARCHAR, row_count BIGINT)"
        )
        connection.execute(
            "INSERT INTO line_items VALUES ('o1', DATE '2025-01-01', 'p1', 'Mug', 1, 1)"
        )
        connection.execute(
            "INSERT INTO order_facts VALUES ('o1', DATE '2025-01-01', DATE '2025-01-01', 1, 1, 1)"
        )
        connection.execute(
            "INSERT INTO dataset_meta VALUES ('legacy', 'USD', TIMESTAMPTZ '2025-01-01 00:00:00+00', "
            "TIMESTAMPTZ '2025-01-02 00:00:00+00', 'hash', 1)"
        )
    finally:
        connection.close()

    connection = duckdb.connect(str(path), read_only=True)
    try:
        metadata = read_meta(connection)
    finally:
        connection.close()
    assert metadata["customer_coverage"] == {
        "tier": "missing",
        "coverage": None,
        "identified_orders": 0,
        "unidentified_orders": 1,
        "total_orders": 1,
    }
