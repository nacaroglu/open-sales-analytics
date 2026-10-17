from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.products.share import read_product_share
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


def row(order, day, product, price):
    return (order, day, product, f"Name {product}", 1, price)


def test_share_and_pareto_use_exact_ordered_gross_sales(tmp_path):
    connection = build(
        tmp_path / "share.duckdb",
        [
            row("o1", date(2025, 1, 1), "a", "50.00"),
            row("o2", date(2025, 1, 2), "b", "20.00"),
            row("o3", date(2025, 1, 3), "c", "15.00"),
            row("o4", date(2025, 1, 4), "d", "10.00"),
            row("o5", date(2025, 1, 5), "e", "5.00"),
        ],
    )
    try:
        result = read_product_share(connection, date(2025, 1, 1), date(2025, 1, 5))
    finally:
        connection.close()

    assert result["product_count"] == 5
    assert result["total_gross_sales"] == Decimal("100.0000")
    assert [row["gross_sales_share"] for row in result["products"]] == [
        Decimal("0.500000"),
        Decimal("0.200000"),
        Decimal("0.150000"),
        Decimal("0.100000"),
        Decimal("0.050000"),
    ]
    assert [row["cumulative_share"] for row in result["products"]] == [
        Decimal("0.500000"),
        Decimal("0.700000"),
        Decimal("0.850000"),
        Decimal("0.950000"),
        Decimal("1.000000"),
    ]
    assert result["top_20_percent_product_count"] == 1
    assert result["top_20_percent_share"] == Decimal("0.500000")
    assert result["products_to_80_percent"] == 3


def test_share_handles_zero_sales_and_empty_ranges(tmp_path):
    connection = build(
        tmp_path / "zero.duckdb",
        [
            row("o1", date(2025, 1, 1), "a", "0.00"),
            row("o2", date(2025, 1, 2), "b", "0.00"),
        ],
    )
    try:
        zero = read_product_share(connection, date(2025, 1, 1), date(2025, 1, 2))
        empty = read_product_share(connection, date(2025, 1, 3), date(2025, 1, 4))
    finally:
        connection.close()

    assert zero["availability"].state.value == "insufficient_data"
    assert zero["availability"].reason == "Gross sales in this range are zero."
    assert zero["product_count"] == 2
    assert all(row["gross_sales_share"] is None for row in zero["products"])
    assert zero["top_20_percent_share"] is None
    assert zero["products_to_80_percent"] is None
    assert empty["availability"].state.value == "zero_result"
    assert empty["products"] == []
    assert empty["product_count"] == 0


def test_share_uses_product_id_order_at_boundaries_and_exact_eighty(tmp_path):
    connection = build(
        tmp_path / "boundary.duckdb",
        [
            row("o1", date(2025, 1, 1), "p2", "40.00"),
            row("o2", date(2025, 1, 2), "p10", "40.00"),
            row("o3", date(2025, 1, 3), "p3", "20.00"),
            row("out", date(2025, 1, 4), "outside", "100.00"),
        ],
    )
    try:
        result = read_product_share(connection, date(2025, 1, 1), date(2025, 1, 3))
    finally:
        connection.close()

    assert [row["product_id"] for row in result["products"]] == ["p10", "p2", "p3"]
    assert result["top_20_percent_product_count"] == 1
    assert result["top_20_percent_share"] == Decimal("0.400000")
    assert result["products_to_80_percent"] == 2
