import csv
import json
from pathlib import Path

import pytest
from app.config import Settings, get_settings
from app.main import app
from fastapi.testclient import TestClient

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


@pytest.fixture
def fixture_client(tmp_path):
    settings = Settings(DATASET_DIR=tmp_path / "data", MAX_UPLOAD_BYTES=10_000, MAX_ROWS=1000)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, settings
    app.dependency_overrides.clear()


def upload_fixture(client: TestClient, name: str):
    return client.post(
        "/api/datasets",
        data={"currency": "USD"},
        files={"file": (name, (FIXTURES / name).read_bytes(), "text/csv")},
    )


def test_customer_fixtures_cover_import_rejection_and_coverage_tiers(fixture_client):
    client, settings = fixture_client
    expected_tiers = {
        "all_blank_customer_ids.csv": "suppressed",
        "coverage_below_50.csv": "suppressed",
        "coverage_exactly_50.csv": "warning",
        "coverage_low.csv": "warning",
        "coverage_exactly_80.csv": "normal",
        "opaque_ids_accepted.csv": "normal",
        "max_length_customer_id.csv": "normal",
        "golden_customers.csv": "normal",
    }
    for name, tier in expected_tiers.items():
        response = upload_fixture(client, name)
        assert response.status_code == 201, (name, response.text)
        assert response.json()["meta"]["customer_coverage"]["tier"] == tier
        dataset_id = response.json()["dataset_id"]
        assert (settings.dataset_dir / f"{dataset_id}.duckdb").exists()

    missing = upload_fixture(client, "no_customer_column.csv")
    assert missing.status_code == 201
    assert missing.json()["meta"]["customer_coverage"]["tier"] == "missing"

    filled = upload_fixture(client, "fill_blank_within_order.csv")
    assert filled.status_code == 201
    assert filled.json()["meta"]["customer_coverage"]["identified_orders"] == 1


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("conflicting_ids_in_order.csv", "conflicting_customer_id"),
        ("email_customer_id.csv", "customer_id_looks_like_email"),
        ("phone_customer_id.csv", "customer_id_looks_like_phone"),
        ("too_long_customer_id.csv", "customer_id_too_long"),
    ],
)
def test_customer_fixtures_reject_invalid_identity_values(fixture_client, name, code):
    client, settings = fixture_client
    response = upload_fixture(client, name)
    assert response.status_code == 422
    assert code in {issue["code"] for issue in response.json()["error"]["errors"]}
    assert not list(settings.dataset_dir.glob("*.duckdb"))
