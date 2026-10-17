from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.products.price_history import read_product_price_history
from app.analytics.shared.buckets import choose_granularity
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


def row(order, day, product, quantity, price):
    return (order, day, product, f"Name {product}", quantity, price)


def test_price_history_uses_weighted_prices_and_contiguous_daily_buckets(tmp_path):
    connection = build(
        tmp_path / "daily.duckdb",
        [
            row("a", date(2025, 1, 1), "p", 2, "10.00"),
            row("b", date(2025, 1, 1), "p", 1, "13.00"),
            row("c", date(2025, 1, 2), "p", 1, "0.00"),
            row("d", date(2025, 1, 2), "p", 2, "10.01"),
        ],
    )
    try:
        result = read_product_price_history(
            connection, "p", date(2025, 1, 1), date(2025, 1, 3), "daily"
        )
    finally:
        connection.close()

    assert result["availability"].state.value == "available"
    assert result["buckets"] == [
        {
            "bucket_start": date(2025, 1, 1),
            "weighted_unit_price": Decimal("11.0000"),
            "units_sold": 3,
        },
        {
            "bucket_start": date(2025, 1, 2),
            "weighted_unit_price": Decimal("6.6733"),
            "units_sold": 3,
        },
        {
            "bucket_start": date(2025, 1, 3),
            "weighted_unit_price": None,
            "units_sold": 0,
        },
    ]


def test_price_history_reuses_weekly_buckets_and_range_boundaries(tmp_path):
    connection = build(
        tmp_path / "weekly.duckdb",
        [
            row("before", date(2025, 1, 5), "p", 1, "100.00"),
            row("inside-1", date(2025, 1, 8), "p", 1, "10.00"),
            row("inside-2", date(2025, 1, 12), "p", 2, "10.01"),
            row("after", date(2025, 1, 15), "p", 1, "90.00"),
        ],
    )
    start, end = date(2025, 1, 8), date(2025, 12, 31)
    try:
        result = read_product_price_history(
            connection, "p", start, end, choose_granularity(start, end)
        )
    finally:
        connection.close()

    assert result["granularity"] == "weekly"
    assert result["buckets"][0] == {
        "bucket_start": date(2025, 1, 6),
        "weighted_unit_price": Decimal("10.0067"),
        "units_sold": 3,
    }
    assert result["buckets"][1]["weighted_unit_price"] == Decimal("90.0000")


def test_price_history_is_zero_result_when_product_has_no_lines_in_range(tmp_path):
    connection = build(
        tmp_path / "empty-range.duckdb",
        [row("outside", date(2025, 1, 1), "p", 1, "20.00")],
    )
    try:
        result = read_product_price_history(
            connection, "p", date(2025, 1, 2), date(2025, 1, 2), "daily"
        )
    finally:
        connection.close()

    assert result["availability"].state.value == "zero_result"
    assert result["buckets"] == [
        {"bucket_start": date(2025, 1, 2), "weighted_unit_price": None, "units_sold": 0}
    ]
