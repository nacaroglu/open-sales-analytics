import csv
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "customers"
HEADER = ["order_id", "order_date", "product_id", "product_name", "quantity", "unit_price"]


def rows(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_customer_fixture_catalog_has_one_named_rule_per_file():
    expected = {
        "no_customer_column.csv",
        "all_blank_customer_ids.csv",
        "coverage_below_50.csv",
        "coverage_exactly_50.csv",
        "coverage_low.csv",
        "coverage_exactly_80.csv",
        "fill_blank_within_order.csv",
        "conflicting_ids_in_order.csv",
        "email_customer_id.csv",
        "phone_customer_id.csv",
        "too_long_customer_id.csv",
        "max_length_customer_id.csv",
        "opaque_ids_accepted.csv",
        "immature_cohorts.csv",
        "golden_customers.csv",
    }
    assert {path.name for path in FIXTURES.glob("*.csv")} == expected
    for name in expected:
        path = FIXTURES / name
        assert path.stat().st_size > 0
        assert set(rows(name)[0]) >= set(HEADER)


def test_customer_coverage_fixtures_have_the_documented_order_counts():
    expected = {
        "coverage_below_50.csv": (1, 4),
        "coverage_exactly_50.csv": (2, 4),
        "coverage_low.csv": (7, 10),
        "coverage_exactly_80.csv": (8, 10),
    }
    for name, (identified, total) in expected.items():
        data = rows(name)
        assert len(data) == total
        assert sum(bool(row["customer_id"].strip()) for row in data) == identified


def test_golden_expected_json_is_next_to_the_golden_csv():
    expected = json.loads((FIXTURES / "golden_customers.expected.json").read_text())
    assert expected["coverage"] == {
        "identified_orders": 19,
        "unidentified_orders": 1,
        "total_orders": 20,
    }
    assert expected["customer_count"] == 10
