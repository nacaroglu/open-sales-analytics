from datetime import date
from decimal import Decimal

import duckdb
import pytest

from app.analytics.kpis import read_kpis
from app.schema import create_dataset, open_dataset_readonly

# Hand-written dataset. Worked out by hand for 2026-03-02 .. 2026-03-04:
#   O2 (03-02): 2 x 10.50 + 1 x 3.25          = 24.25   units 3
#   O3 (03-03): 1 x 10.00 (bolt, other price) = 10.00   units 1
#   O4 (03-04): 5 x 0.10                      =  0.50   units 5
#   O5 (03-04): 4 x 0.00 (free gift)          =  0.00   units 4
#   gross 34.75, orders 4, units 13, average 8.6875
# Outside the range: O1 one day before, O6 one day after.
ROWS = [
    ("O1", date(2026, 3, 1), "P1", "Bolt", 100, "1.00"),
    ("O2", date(2026, 3, 2), "P1", "Bolt", 2, "10.50"),
    ("O2", date(2026, 3, 2), "P2", "Nut", 1, "3.25"),
    ("O3", date(2026, 3, 3), "P1", "Bolt", 1, "10.00"),
    ("O4", date(2026, 3, 4), "P3", "Washer", 5, "0.10"),
    ("O5", date(2026, 3, 4), "P4", "Gift", 4, "0.00"),
    ("O6", date(2026, 3, 5), "P1", "Bolt", 100, "1.00"),
]
START, END = date(2026, 3, 2), date(2026, 3, 4)


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        if rows:
            connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()
    return open_dataset_readonly(path)


@pytest.fixture
def connection(tmp_path):
    connection = build(tmp_path / "kpi.duckdb", ROWS)
    yield connection
    connection.close()


def kpis_for(tmp_path, rows, start, end):
    connection = build(tmp_path / "other.duckdb", rows)
    try:
        return read_kpis(connection, start, end)
    finally:
        connection.close()


def test_kpis_over_range(connection):
    result = read_kpis(connection, START, END)
    assert result == {
        "gross_sales": Decimal("34.75"),
        "orders": 4,
        "units_sold": 13,
        "average_order_value": Decimal("8.6875"),
    }


def test_types(connection):
    result = read_kpis(connection, START, END)
    assert type(result["gross_sales"]) is Decimal
    assert type(result["average_order_value"]) is Decimal
    assert type(result["orders"]) is int
    assert type(result["units_sold"]) is int


def test_order_with_three_lines_counts_once(tmp_path):
    rows = [("A", date(2026, 1, 1), f"P{i}", "x", 1, "1.00") for i in range(3)]
    result = kpis_for(tmp_path, rows, date(2026, 1, 1), date(2026, 1, 1))
    assert result["orders"] == 1
    assert result["units_sold"] == 3
    assert result["average_order_value"] == Decimal("3.0000")


def test_boundaries_are_inclusive_and_neighbours_excluded(connection):
    assert read_kpis(connection, date(2026, 3, 1), date(2026, 3, 1))["units_sold"] == 100
    assert read_kpis(connection, date(2026, 3, 2), date(2026, 3, 2))["orders"] == 1
    assert read_kpis(connection, date(2026, 3, 4), date(2026, 3, 4))["orders"] == 2
    assert read_kpis(connection, date(2026, 3, 5), date(2026, 3, 5))["units_sold"] == 100
    # one day outside either end
    assert read_kpis(connection, date(2026, 3, 3), date(2026, 3, 3))["units_sold"] == 1


def test_single_day_returns_that_days_rows(connection):
    result = read_kpis(connection, date(2026, 3, 2), date(2026, 3, 2))
    assert result["gross_sales"] == Decimal("24.25")
    assert result["orders"] == 1
    assert result["units_sold"] == 3
    assert result["average_order_value"] == Decimal("24.2500")


def test_empty_range_is_all_zero(connection):
    result = read_kpis(connection, date(2027, 1, 1), date(2027, 1, 31))
    assert result == {
        "gross_sales": 0,
        "orders": 0,
        "units_sold": 0,
        "average_order_value": 0,
    }
    assert type(result["gross_sales"]) is Decimal
    assert type(result["average_order_value"]) is Decimal
    assert type(result["orders"]) is int
    assert type(result["units_sold"]) is int


def test_empty_dataset_is_all_zero(tmp_path):
    result = kpis_for(tmp_path, [], START, END)
    assert result["orders"] == 0
    assert result["average_order_value"] == Decimal("0")


def test_three_lines_of_ten_cents_are_exact(tmp_path):
    rows = [(f"O{i}", date(2026, 1, 1), "P1", "x", 1, "0.10") for i in range(3)]
    result = kpis_for(tmp_path, rows, date(2026, 1, 1), date(2026, 1, 1))
    assert result["gross_sales"] == Decimal("0.3000")
    assert str(result["gross_sales"]) == "0.3000"


def test_half_at_fifth_decimal_rounds_up(tmp_path):
    # 0.0001 / 2 orders = 0.00005 exactly -> 0.0001 (half-up)
    rows = [
        ("A", date(2026, 1, 1), "P1", "x", 1, "0.0001"),
        ("B", date(2026, 1, 1), "P1", "x", 1, "0.0000"),
    ]
    result = kpis_for(tmp_path, rows, date(2026, 1, 1), date(2026, 1, 1))
    assert result["average_order_value"] == Decimal("0.0001")
    # 0.0003 / 2 = 0.00015 -> 0.0002 (a half-even or float result would differ)
    rows[0] = ("A", date(2026, 1, 1), "P1", "x", 1, "0.0003")
    result = kpis_for(tmp_path, rows, date(2026, 1, 1), date(2026, 1, 1))
    assert result["average_order_value"] == Decimal("0.0002")


def test_same_product_at_two_prices(tmp_path):
    rows = [
        ("A", date(2026, 1, 1), "P1", "x", 2, "1.50"),
        ("B", date(2026, 1, 2), "P1", "x", 3, "2.00"),
    ]
    result = kpis_for(tmp_path, rows, date(2026, 1, 1), date(2026, 1, 2))
    assert result["gross_sales"] == Decimal("9.0000")


def test_zero_price_counts_units_and_orders_not_sales(tmp_path):
    rows = [("A", date(2026, 1, 1), "P1", "gift", 7, "0.00")]
    result = kpis_for(tmp_path, rows, date(2026, 1, 1), date(2026, 1, 1))
    assert result["gross_sales"] == Decimal("0")
    assert result["orders"] == 1
    assert result["units_sold"] == 7
    assert result["average_order_value"] == Decimal("0")


def test_dates_are_bound_parameters():
    import inspect

    from app.analytics import kpis

    source = inspect.getsource(kpis)
    assert "BETWEEN ? AND ?" in source
    assert "f\"" not in source and "f'" not in source and ".format(" not in source
