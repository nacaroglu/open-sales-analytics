from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.products.top_products import read_product_rankings
from app.schema import create_dataset, open_dataset_readonly

START = date(2025, 3, 1)
END = date(2025, 3, 7)


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()
    return open_dataset_readonly(path)


def row(order, day, product, quantity, price):
    return (order, day, product, f"Name {product}", quantity, price)


def test_rankings_return_all_values_with_independent_tie_ordering(tmp_path):
    connection = build(
        tmp_path / "rankings.duckdb",
        [
            row("o1", date(2025, 3, 1), "p10", 2, "10.00"),
            row("o2", date(2025, 3, 2), "p2", 2, "10.00"),
            row("o3", date(2025, 3, 3), "p3", 2, "0.00"),
            row("o4", date(2025, 3, 4), "p3", 3, "0.00"),
            row("o5", date(2025, 3, 5), "p4", 5, "1.00"),
            row("o6", date(2025, 3, 6), "p5", 1, "10.00"),
            row("o7", date(2025, 3, 6), "p5", 1, "0.00"),
            row("o8", date(2025, 3, 7), "p5", 1, "0.00"),
            row("before", date(2025, 2, 28), "outside", 99, "99.00"),
            row("after", date(2025, 3, 8), "outside", 99, "99.00"),
        ],
    )
    try:
        rankings = read_product_rankings(connection, START, END)
    finally:
        connection.close()

    assert [row["product_id"] for row in rankings["by_gross_sales"]] == [
        "p10",
        "p2",
        "p5",
        "p4",
        "p3",
    ]
    assert [row["product_id"] for row in rankings["by_units_sold"]] == [
        "p3",
        "p4",
        "p5",
        "p10",
        "p2",
    ]
    assert [row["product_id"] for row in rankings["by_orders"]] == [
        "p5",
        "p3",
        "p10",
        "p2",
        "p4",
    ]
    assert rankings["by_gross_sales"][0] == {
        "product_id": "p10",
        "product_name": "Name p10",
        "gross_sales": Decimal("20.0000"),
        "units_sold": 2,
        "distinct_orders": 1,
    }
    assert rankings["by_gross_sales"][-1]["gross_sales"] == Decimal("0.0000")


def test_rankings_exclude_products_outside_an_empty_range(tmp_path):
    connection = build(
        tmp_path / "empty.duckdb",
        [row("o1", date(2025, 3, 1), "p1", 1, "1.00")],
    )
    try:
        rankings = read_product_rankings(connection, date(2025, 3, 2), date(2025, 3, 3))
    finally:
        connection.close()

    assert rankings == {"by_gross_sales": [], "by_units_sold": [], "by_orders": []}
