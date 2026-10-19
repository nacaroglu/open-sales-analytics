from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.products.basket import read_product_basket
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


def row(order, product, price="1.00"):
    return (order, date(2025, 1, 1), product, f"Name {product}", 1, price)


def test_basket_returns_exact_thresholded_pairs_and_lift_ranking(tmp_path):
    rows = []
    for index in range(10):
        rows.extend([row(f"ab-{index}", "a"), row(f"ab-{index}", "b")])
    for index in range(5):
        rows.append(row(f"a-only-{index}", "a"))
        rows.append(row(f"b-only-{index}", "b"))
    for index in range(10):
        rows.extend([row(f"cd-{index}", "c"), row(f"cd-{index}", "d")])
    for index in range(9):
        rows.extend([row(f"ef-{index}", "e"), row(f"ef-{index}", "f")])
    connection = build(tmp_path / "basket.duckdb", rows)
    try:
        result = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()

    assert result["basket_orders"] == 39
    assert result["eligible_pair_count"] == 2
    assert result["availability"].state.value == "available"
    assert [pair["product_a"]["product_id"] for pair in result["pairs"]] == ["c", "a"]
    assert result["pairs"][0] == {
        "product_a": {"product_id": "c", "product_name": "Name c"},
        "product_b": {"product_id": "d", "product_name": "Name d"},
        "shared_orders": 10,
        "support": Decimal("0.256410"),
        "confidence_a_to_b": Decimal("1.000000"),
        "confidence_b_to_a": Decimal("1.000000"),
        "lift": Decimal("3.900000"),
    }
    assert result["pairs"][1]["shared_orders"] == 10
    assert result["pairs"][1]["support"] == Decimal("0.256410")


def test_basket_related_products_use_product_perspective_and_same_values(tmp_path):
    rows = []
    for index in range(10):
        rows.extend([row(f"ab-{index}", "a"), row(f"ab-{index}", "b", "0.00")])
    for index in range(5):
        rows.append(row(f"a-only-{index}", "a"))
    connection = build(tmp_path / "related.duckdb", rows)
    try:
        result = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1), product_id="b")
    finally:
        connection.close()

    assert result["related_products"] == [
        {
            "product": {"product_id": "a", "product_name": "Name a"},
            "shared_orders": 10,
            "support": Decimal("0.666667"),
            "confidence_from_x": Decimal("1.000000"),
            "confidence_to_x": Decimal("0.666667"),
            "lift": Decimal("1.000000"),
        }
    ]
    assert result["related_availability"].state.value == "available"


def test_basket_availability_distinguishes_empty_small_and_no_pair(tmp_path):
    connection = build(
        tmp_path / "availability.duckdb",
        [row(f"o-{index}", "a") for index in range(9)],
    )
    try:
        small = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()
    assert small["availability"].state.value == "insufficient_data"
    assert small["pairs"] == []

    connection = build(
        tmp_path / "no-pair.duckdb",
        [row(f"o-{index}", "a") for index in range(10)],
    )
    try:
        no_pair = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()
    assert no_pair["availability"].state.value == "zero_result"


def test_basket_support_boundary_is_exact(tmp_path):
    rows = [row(f"shared-{index}", "a") for index in range(10)]
    rows += [row(f"shared-{index}", "b") for index in range(10)]
    rows += [row(f"single-{index}", "single") for index in range(9990)]
    connection = build(tmp_path / "support.duckdb", rows)
    try:
        result = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()
    assert result["basket_orders"] == 10000
    assert result["pairs"][0]["support"] == Decimal("0.001000")


def test_basket_support_below_boundary_is_excluded(tmp_path):
    rows = [row(f"shared-{index}", "a") for index in range(10)]
    rows += [row(f"shared-{index}", "b") for index in range(10)]
    rows += [row(f"single-{index}", "single") for index in range(9991)]
    connection = build(tmp_path / "support-below.duckdb", rows)
    try:
        result = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()
    assert result["basket_orders"] == 10001
    assert result["eligible_pair_count"] == 0
    assert result["pairs"] == []


def test_oversize_orders_are_excluded_once_and_disclosed(tmp_path):
    rows = []
    for index in range(9):
        rows.extend([row(f"small-{index}", "a"), row(f"small-{index}", "b")])
    rows.extend([row("exactly-100", "a"), row("exactly-100", "b")])
    rows.extend(row("exactly-100", f"p-{index}") for index in range(98))
    rows.extend([row("oversize-101", "a"), row("oversize-101", "b")])
    rows.extend(row("oversize-101", f"q-{index}") for index in range(99))
    connection = build(tmp_path / "oversize.duckdb", rows)
    try:
        result = read_product_basket(connection, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()

    assert result["excluded_oversize_orders"] == 1
    assert result["basket_orders"] == 10
    assert result["pairs"][0]["shared_orders"] == 10
