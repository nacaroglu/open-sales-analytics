from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.products.growth import read_product_growth
from app.analytics.shared.periods import comparison_period, resolve_reporting_range
from app.schema import create_dataset, open_dataset_readonly


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        connection.executemany(
            "INSERT INTO line_items (order_id, order_date, product_id, product_name, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    finally:
        connection.close()
    return open_dataset_readonly(path)


def row(order, day, product, price, quantity=1):
    return (order, day, product, f"Name {product}", quantity, price)


def periods(start, end, mode="previous_period"):
    current = resolve_reporting_range(start, end, date(2025, 1, 1), date(2025, 1, 10))
    return current, comparison_period(current, mode, date(2025, 1, 1))


def test_growth_uses_union_periods_and_classifies_products(tmp_path):
    connection = build(
        tmp_path / "growth.duckdb",
        [
            row("old-a", date(2025, 1, 5), "a", "10.00"),
            row("old-b", date(2025, 1, 6), "b", "20.00"),
            row("old-c", date(2025, 1, 7), "c", "5.00"),
            row("new-a", date(2025, 1, 8), "a", "25.00"),
            row("new-c", date(2025, 1, 9), "c", "0.00"),
            row("new-d", date(2025, 1, 10), "d", "7.00"),
        ],
    )
    current, comparison = periods(date(2025, 1, 8), date(2025, 1, 10))
    try:
        result = read_product_growth(connection, current, comparison)
    finally:
        connection.close()

    assert result["availability"].state.value == "available"
    assert [product["product_id"] for product in result["products"]] == ["a", "b", "c", "d"]
    by_id = {product["product_id"]: product for product in result["products"]}
    assert by_id["a"]["classification"] == "rising"
    assert by_id["a"]["gross_sales"] == {
        "value": Decimal("25.0000"),
        "comparison_value": Decimal("10.0000"),
        "absolute_change": Decimal("15.0000"),
        "percent_change": Decimal("150.00"),
        "change_status": "comparable",
    }
    assert by_id["b"]["classification"] == "no_current_sales"
    assert by_id["b"]["gross_sales"]["change_status"] == "comparable"
    assert by_id["c"]["classification"] == "falling"
    assert by_id["d"]["classification"] == "new"
    assert by_id["d"]["gross_sales"]["change_status"] == "new"
    assert [product["product_id"] for product in result["rising"]] == ["a", "d"]
    assert [product["product_id"] for product in result["falling"]] == ["b", "c"]


def test_growth_nulls_comparison_when_period_is_unavailable(tmp_path):
    connection = build(
        tmp_path / "unavailable.duckdb",
        [row("current", date(2025, 1, 8), "a", "12.00")],
    )
    current = resolve_reporting_range(
        date(2025, 1, 8), date(2025, 1, 10), date(2025, 1, 8), date(2025, 1, 10)
    )
    comparison = comparison_period(current, "previous_period", date(2025, 1, 8))
    try:
        result = read_product_growth(connection, current, comparison)
    finally:
        connection.close()

    product = result["products"][0]
    assert result["availability"].state.value == "available"
    assert product["classification"] is None
    assert product["gross_sales"]["value"] == Decimal("12.0000")
    assert product["gross_sales"]["comparison_value"] is None
    assert product["gross_sales"]["change_status"] is None
    assert result["rising"] == []
    assert result["falling"] == []


def test_growth_supports_previous_year_and_empty_ranges(tmp_path):
    connection = build(
        tmp_path / "year.duckdb",
        [
            row("old", date(2025, 1, 2), "a", "10.00"),
            row("current", date(2025, 1, 2), "a", "20.00"),
        ],
    )
    current = resolve_reporting_range(
        date(2025, 1, 2), date(2025, 1, 2), date(2025, 1, 1), date(2025, 1, 10)
    )
    year = comparison_period(current, "previous_year", date(2024, 1, 1))
    try:
        result = read_product_growth(connection, current, year)
    finally:
        connection.close()

    assert result["products"][0]["gross_sales"]["comparison_value"] == Decimal("0.0000")
    assert result["products"][0]["gross_sales"]["change_status"] == "new"

    create_dataset(tmp_path / "empty.duckdb")
    connection = open_dataset_readonly(tmp_path / "empty.duckdb")
    try:
        empty = read_product_growth(connection, current, year)
    finally:
        connection.close()
    assert empty["availability"].state.value == "zero_result"
    assert empty["products"] == []
