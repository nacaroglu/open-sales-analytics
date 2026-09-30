import inspect
from datetime import date
from decimal import Decimal

import duckdb
import pytest
from app.analytics import top_products
from app.analytics.top_products import read_top_products
from app.schema import create_dataset, open_dataset_readonly

DAY = date(2025, 3, 10)


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        if rows:
            connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()
    return open_dataset_readonly(path)


def top_for(tmp_path, rows, start=DAY, end=DAY, **kwargs):
    connection = build(tmp_path / "top.duckdb", rows)
    try:
        return read_top_products(connection, start, end, **kwargs)
    finally:
        connection.close()


def sale(pid, price, order="O1", day=DAY, quantity=1, name=None):
    return (order, day, pid, name or f"Name {pid}", quantity, price)


def ids(result):
    return [item["product_id"] for item in result]


def test_orders_by_gross_sales_descending_with_full_shape(tmp_path):
    rows = [
        sale("a", "5.00", "O1", quantity=2),
        sale("a", "5.00", "O2", quantity=1),
        sale("b", "100.5000", "O1"),
        sale("c", "1.00", "O3"),
    ]
    result = top_for(tmp_path, rows)
    assert ids(result) == ["b", "a", "c"]
    assert result[1] == {
        "product_id": "a",
        "product_name": "Name a",
        "gross_sales": Decimal("15"),
        "units_sold": 3,
        "distinct_orders": 2,
    }
    assert isinstance(result[0]["gross_sales"], Decimal)
    assert type(result[0]["units_sold"]) is int
    assert type(result[0]["distinct_orders"]) is int


def test_tie_broken_by_product_id_as_text(tmp_path):
    rows = [sale("p2", "10.00"), sale("p10", "10.00"), sale("p1", "10.00")]
    assert ids(top_for(tmp_path, rows)) == ["p1", "p10", "p2"]


def test_n_smaller_than_product_count_drops_lowest(tmp_path):
    rows = [sale(f"p{i:02d}", f"{i}.00") for i in range(1, 13)]
    result = top_for(tmp_path, rows, n=10)
    assert len(result) == 10
    assert "p01" not in ids(result) and "p02" not in ids(result)
    assert ids(result)[0] == "p12"


def test_default_n_is_ten(tmp_path):
    rows = [sale(f"p{i:02d}", f"{i}.00") for i in range(1, 13)]
    assert len(top_for(tmp_path, rows)) == 10


def test_n_larger_than_product_count_is_not_padded(tmp_path):
    rows = [sale(f"p{i}", f"{i}.00") for i in range(1, 5)]
    assert len(top_for(tmp_path, rows, n=10)) == 4


def test_tie_at_cutoff_keeps_lower_product_id(tmp_path):
    # 9 clear leaders, then p2 / p10 / p3 tie for the 10th slot.
    rows = [sale(f"q{i}", f"{100 + i}.00") for i in range(9)]
    rows += [sale("p2", "5.00"), sale("p10", "5.00"), sale("p3", "5.00")]
    result = top_for(tmp_path, rows, n=10)
    assert len(result) == 10
    assert ids(result)[-1] == "p10"
    assert "p2" not in ids(result)


def test_no_sales_gives_empty_list(tmp_path):
    assert top_for(tmp_path, []) == []
    assert top_for(tmp_path, [sale("a", "1.00", day=date(2025, 1, 1))]) == []


def test_range_is_inclusive_and_excludes_outside(tmp_path):
    rows = [
        sale("in1", "1.00", day=date(2025, 3, 1)),
        sale("in2", "1.00", day=date(2025, 3, 31)),
        sale("before", "1.00", day=date(2025, 2, 28)),
        sale("after", "1.00", day=date(2025, 4, 1)),
    ]
    result = top_for(tmp_path, rows, date(2025, 3, 1), date(2025, 3, 31))
    assert ids(result) == ["in1", "in2"]


def test_zero_price_product_appears_with_zero_if_room(tmp_path):
    rows = [sale("free", "0.00", quantity=3), sale("paid", "2.00")]
    result = top_for(tmp_path, rows, n=10)
    assert ids(result) == ["paid", "free"]
    assert result[1]["gross_sales"] == Decimal("0")
    assert result[1]["units_sold"] == 3
    assert ids(top_for(tmp_path, rows, n=1)) == ["paid"]


def test_same_name_different_ids_are_separate(tmp_path):
    rows = [sale("a", "2.00", name="Bolt"), sale("b", "1.00", name="Bolt")]
    result = top_for(tmp_path, rows)
    assert [(i["product_id"], i["product_name"]) for i in result] == [("a", "Bolt"), ("b", "Bolt")]


def test_distinct_orders_counts_each_order_once(tmp_path):
    rows = [sale("a", "1.00", "O1"), sale("a", "1.00", "O1"), sale("a", "1.00", "O2")]
    assert top_for(tmp_path, rows)[0]["distinct_orders"] == 2


def test_money_is_exact(tmp_path):
    rows = [sale("a", "0.1000") for _ in range(3)]
    assert top_for(tmp_path, rows)[0]["gross_sales"] == Decimal("0.3")


def test_name_choice_is_deterministic_if_an_id_has_two_names(tmp_path):
    rows = [sale("a", "1.00", name="Zed"), sale("a", "1.00", name="Abe")]
    assert top_for(tmp_path, rows)[0]["product_name"] == "Abe"


@pytest.mark.parametrize("n", [0, -1])
def test_n_below_one_raises(tmp_path, n):
    with pytest.raises(ValueError):
        top_for(tmp_path, [], n=n)


def test_start_end_and_n_are_bound_parameters():
    sql = top_products._TOP_PRODUCTS_SQL
    assert sql.count("?") == 3
    assert "{" not in sql and "%" not in sql
    assert "execute(_TOP_PRODUCTS_SQL, [start, end, n])" in inspect.getsource(read_top_products)
