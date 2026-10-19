from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pytest
from app.analytics.customers.concentration import read_concentration
from app.analytics.shared.metrics import METRICS
from app.api.customers import _concentration_body
from app.api.module_common import resolve_periods
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(LINE_ITEMS_DDL)
    connection.execute(ORDER_FACTS_DDL)
    connection.execute(CUSTOMER_FACTS_DDL)
    if rows:
        connection.executemany(
            "INSERT INTO line_items (order_id, order_date, product_id, product_name, quantity, unit_price, customer_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return connection


def sales_rows(values, start=date(2025, 1, 1)):
    return [
        (f"o{index}", start + timedelta(days=index), "p", "Product", 1, str(value), f"C{index}")
        for index, value in enumerate(values, 1)
    ]


def test_concentration_uses_ceil_decile_and_rounds_the_share():
    connection = connection_with_rows(
        sales_rows([1000, 500, 100, 100, 100, 100, 100, 100, 100, 100])
    )
    try:
        result = read_concentration(connection, date(2025, 1, 1), date(2025, 1, 31))
    finally:
        connection.close()
    assert result == {
        "customer_count": 10,
        "top_decile_customer_count": 1,
        "top_decile_gross_sales": Decimal("1000.0000"),
        "identified_gross_sales": Decimal("2300.0000"),
    }
    assert (
        round(float(result["top_decile_gross_sales"] / result["identified_gross_sales"]), 4)
        == 0.4348
    )


def test_concentration_handles_ceil_eleven_customers_ties_and_date_boundaries():
    rows = sales_rows([1000, 500, 100, 100, 100, 100, 100, 100, 100, 100])
    rows.append(("outside", date(2024, 12, 31), "p", "Product", 1, "50.00", "C11"))
    connection = connection_with_rows(rows)
    try:
        result = read_concentration(connection, date(2025, 1, 1), date(2025, 1, 31))
    finally:
        connection.close()
    assert result["customer_count"] == 10
    assert result["top_decile_customer_count"] == 1
    assert result["top_decile_gross_sales"] == Decimal("1000.0000")

    tied = connection_with_rows(sales_rows([900, 400, 400, *([10] * 17)]))
    try:
        result = read_concentration(tied, date(2025, 1, 1), date(2025, 1, 31))
    finally:
        tied.close()
    assert result["top_decile_customer_count"] == 2
    assert result["top_decile_gross_sales"] == Decimal("1300.0000")
    assert result["identified_gross_sales"] == Decimal("1870.0000")


@pytest.mark.parametrize("count", [0, 9])
def test_concentration_requires_ten_active_customers(count):
    connection = connection_with_rows(sales_rows([1] * count))
    try:
        periods = resolve_periods(
            "2025-01-01", "2025-01-31", "previous_period", date(2025, 1, 1), date(2025, 1, 31)
        )
        body = _concentration_body(connection, periods)
    finally:
        connection.close()
    assert body["availability"] == {
        "state": "insufficient_data",
        "reason": "Concentration needs at least 10 identified customers in the range.",
    }
    assert body["top_decile_share"] is None


def test_concentration_zero_sales_is_insufficient_without_nan():
    connection = connection_with_rows(sales_rows([0] * 10))
    try:
        periods = resolve_periods(
            "2025-01-01", "2025-01-31", "previous_period", date(2025, 1, 1), date(2025, 1, 31)
        )
        body = _concentration_body(connection, periods)
    finally:
        connection.close()
    assert body["availability"]["state"] == "insufficient_data"
    assert body["top_decile_share"] is None
    assert body["top_decile_gross_sales"] == "0.0000"


def test_concentration_metric_definition_is_registered():
    metric = METRICS["concentration"]
    assert metric.unit == "ratio"
    assert "ceil(N / 10)" in metric.formula
    assert (
        metric.numerator and metric.denominator and metric.time_window and metric.insufficient_data
    )
