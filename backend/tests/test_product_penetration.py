from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.products.penetration import read_product_penetration
from app.schema import create_dataset, open_dataset_readonly


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()
    return open_dataset_readonly(path)


def row(order, day, product, price="1.00"):
    return (order, day, product, f"Name {product}", 1, price)


def test_penetration_uses_distinct_in_range_orders_and_exact_fractions(tmp_path):
    rows = [row(f"o{index}", date(2025, 1, index), "all") for index in range(1, 9)]
    rows += [row("o1", date(2025, 1, 1), "three"), row("o2", date(2025, 1, 2), "three")]
    rows += [row("o3", date(2025, 1, 3), "three")]
    rows += [row("o1", date(2025, 1, 1), "one", "0.00")]
    rows += [row("o4", date(2025, 1, 4), "tie")]
    rows += [row("o1", date(2025, 1, 10), "one", "10.00")]
    connection = build(tmp_path / "penetration.duckdb", rows)
    try:
        result = read_product_penetration(connection, date(2025, 1, 1), date(2025, 1, 8))
    finally:
        connection.close()

    assert result["all_orders"] == 8
    assert [product["product_id"] for product in result["products"]] == [
        "all",
        "three",
        "one",
        "tie",
    ]
    by_id = {product["product_id"]: product for product in result["products"]}
    assert by_id["all"]["order_penetration"] == Decimal("1.000000")
    assert by_id["three"]["order_penetration"] == Decimal("0.375000")
    assert by_id["one"]["order_penetration"] == Decimal("0.125000")
    assert by_id["one"]["orders_containing_product"] == 1
    assert all(product["order_penetration"] <= 1 for product in result["products"])


def test_penetration_supports_filtered_order_population_and_product_zero(tmp_path):
    connection = build(
        tmp_path / "population.duckdb",
        [
            row("o1", date(2025, 1, 1), "p"),
            row("o2", date(2025, 1, 2), "p"),
            row("o3", date(2025, 1, 3), "other"),
            row("o4", date(2025, 1, 4), "outside"),
        ],
    )
    try:
        filtered = read_product_penetration(
            connection,
            date(2025, 1, 1),
            date(2025, 1, 3),
            order_population={"o1", "o2"},
            product_id="other",
        )
        no_lines = read_product_penetration(
            connection,
            date(2025, 1, 1),
            date(2025, 1, 3),
            product_id="outside",
        )
    finally:
        connection.close()

    assert filtered["all_orders"] == 2
    assert filtered["products"][0]["orders_containing_product"] == 0
    assert filtered["products"][0]["order_penetration"] == Decimal("0.000000")
    assert no_lines["all_orders"] == 3
    assert no_lines["products"][0]["orders_containing_product"] == 0
    assert no_lines["products"][0]["order_penetration"] == Decimal("0.000000")


def test_penetration_has_zero_result_when_no_orders_exist(tmp_path):
    connection = build(
        tmp_path / "empty-range.duckdb",
        [row("outside", date(2025, 1, 10), "p")],
    )
    try:
        result = read_product_penetration(connection, date(2025, 1, 1), date(2025, 1, 2))
    finally:
        connection.close()

    assert result["all_orders"] == 0
    assert result["availability"].state.value == "zero_result"
    assert result["products"] == []
