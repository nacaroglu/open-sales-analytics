from datetime import date, timedelta
from decimal import Decimal

import duckdb
from app.analytics.products.dormancy import read_dormant_products
from app.analytics.shared.periods import ReportingRange
from app.schema import create_dataset, open_dataset_readonly


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()
    return open_dataset_readonly(path)


def row(order, day, product, price):
    return (order, day, product, f"Name {product}", 1, price)


def test_dormancy_uses_anchor_history_and_exact_boundaries(tmp_path):
    anchor = date(2024, 3, 31)
    connection = build(
        tmp_path / "dormancy.duckdb",
        [
            row("p30", anchor - timedelta(days=29), "p30", "4.00"),
            row("p59", anchor - timedelta(days=59), "p59", "5.00"),
            row("p60", anchor - timedelta(days=60), "p60", "10.00"),
            row("p75", anchor - timedelta(days=75), "p75", "30.00"),
            row("p90", anchor - timedelta(days=90), "p90", "20.00"),
            row("today", anchor, "today", "1.00"),
            row("future", anchor + timedelta(days=1), "future", "100.00"),
        ],
    )
    reporting_range = ReportingRange(anchor - timedelta(days=10), anchor, 11)
    try:
        at_30 = read_dormant_products(connection, reporting_range, 30)
        at_60 = read_dormant_products(connection, reporting_range, 60)
        at_90 = read_dormant_products(connection, reporting_range, 90)
    finally:
        connection.close()

    assert [product["product_id"] for product in at_30["products"]] == [
        "p75",
        "p90",
        "p60",
        "p59",
    ]
    assert [product["product_id"] for product in at_60["products"]] == ["p75", "p90", "p60"]
    assert [product["product_id"] for product in at_90["products"]] == ["p90"]
    assert at_60["products"][-1] == {
        "product_id": "p60",
        "product_name": "Name p60",
        "last_sale_date": anchor - timedelta(days=60),
        "days_inactive": 60,
        "earlier_gross_sales": Decimal("10.0000"),
        "earlier_orders": 1,
    }
    assert at_60["anchor_date"] == anchor


def test_dormancy_reports_zero_price_and_history_ordering(tmp_path):
    anchor = date(2024, 3, 31)
    connection = build(
        tmp_path / "ordering.duckdb",
        [
            row("zero", anchor - timedelta(days=75), "zero", "0.00"),
            row("large-1", anchor - timedelta(days=80), "large", "8.00"),
            row("large-2", anchor - timedelta(days=70), "large", "7.00"),
        ],
    )
    try:
        result = read_dormant_products(connection, ReportingRange(anchor, anchor, 1), 60)
    finally:
        connection.close()

    assert [product["product_id"] for product in result["products"]] == ["large", "zero"]
    assert result["products"][-1]["earlier_gross_sales"] == Decimal("0.0000")
    assert result["products"][0]["earlier_gross_sales"] == Decimal("15.0000")


def test_dormancy_distinguishes_insufficient_history_and_zero_result(tmp_path):
    anchor = date(2024, 3, 31)
    connection = build(
        tmp_path / "availability.duckdb",
        [row("recent", anchor - timedelta(days=10), "recent", "1.00")],
    )
    try:
        insufficient = read_dormant_products(connection, ReportingRange(anchor, anchor, 1), 60)
    finally:
        connection.close()
    assert insufficient["availability"].state.value == "insufficient_data"
    assert (
        insufficient["availability"].reason
        == "The data covers fewer than 60 days before 2024-03-31."
    )

    connection = build(
        tmp_path / "zero-result.duckdb",
        [
            row("recent", anchor - timedelta(days=10), "recent", "1.00"),
            row("old", anchor - timedelta(days=100), "old", "1.00"),
            row("old-current", anchor, "old", "1.00"),
        ],
    )
    try:
        zero = read_dormant_products(connection, ReportingRange(anchor, anchor, 1), 90)
    finally:
        connection.close()
    assert zero["availability"].state.value == "zero_result"
    assert zero["products"] == []
