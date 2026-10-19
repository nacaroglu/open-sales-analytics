import csv
import json
from collections import Counter
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "customers"


def test_golden_customer_fixture_covers_the_release_rules():
    with (FIXTURES / "golden_customers.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    orders = Counter(row["order_id"] for row in rows)
    customers = {row["customer_id"] for row in rows if row["customer_id"]}
    assert len(orders) == 20
    assert len(customers) == 10
    assert any(row["order_date"] < "2025-01-01" for row in rows)
    assert any(not row["customer_id"] for row in rows)

    expected = json.loads((FIXTURES / "golden_customers.expected.json").read_text())
    assert expected["customer_count"] == len(customers)
    assert expected["coverage"]["total_orders"] == len(orders)
