from datetime import UTC, datetime

import pytest
from app.auth import get_now
from app.config import Settings, get_settings
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from fastapi.testclient import TestClient

REQUIRED = "order_id,order_date,product_id,product_name,quantity,unit_price"
CUSTOMER_HEADER = REQUIRED + ",customer_id"
NOW = datetime(2026, 10, 19, tzinfo=UTC)


@pytest.fixture
def client(tmp_path):
    settings = Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_response_cache] = lambda: ResponseCache(
        max_entries=20, ttl_seconds=300
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(client, rows, header=CUSTOMER_HEADER):
    response = client.post(
        "/api/datasets",
        files={
            "file": (
                "projection.csv",
                (header + "\n" + "\n".join(rows) + "\n").encode(),
                "text/csv",
            )
        },
        data={"currency": "EUR"},
    )
    assert response.status_code == 201
    return response.json()


def get_customers(client, dataset, **params):
    return client.get(
        f"/api/datasets/{dataset['dataset_id']}/customers",
        params=params,
        headers={"Authorization": f"Bearer {dataset['token']}"},
    )


def test_projection_block_is_unavailable_without_customer_ids(client):
    dataset = upload(
        client,
        ["o1,2025-01-01,p1,Mug,1,2.00", "o2,2025-02-01,p1,Mug,1,3.00"],
        header=REQUIRED,
    )
    body = get_customers(client, dataset, start="2025-01-01", end="2025-02-01").json()

    projection = body["projected_12_month_customer_value"]
    assert projection["is_estimate"] is True
    assert projection["horizon_months"] == 12
    assert projection["data_cutoff"] == "2025-02-01"
    assert projection["eligibility"]["status"] == "unavailable"
    assert projection["value"] is None


def test_projection_block_is_ineligible_and_uses_end_as_cutoff(client):
    dataset = upload(
        client,
        [
            "o1,2025-01-01,p1,Mug,1,2.00,CUSTOMER-SECRET-001",
            "o2,2025-02-01,p1,Mug,1,3.00,CUSTOMER-SECRET-002",
        ],
    )
    narrow = get_customers(client, dataset, start="2025-02-01", end="2025-02-01")
    wide = get_customers(client, dataset, start="2025-01-01", end="2025-02-01")

    assert narrow.status_code == wide.status_code == 200
    narrow_projection = narrow.json()["projected_12_month_customer_value"]
    wide_projection = wide.json()["projected_12_month_customer_value"]
    assert narrow_projection == wide_projection
    assert narrow_projection["data_cutoff"] == "2025-02-01"
    assert narrow_projection["eligibility"]["status"] == "ineligible"
    assert len(narrow_projection["eligibility"]["conditions"]) == 4
    assert narrow_projection["value"] is None
    assert "CUSTOMER-SECRET" not in wide.text


def test_projection_estimate_fields_are_described_in_openapi():
    schema = app.openapi()["components"]["schemas"]["Projected12MonthCustomerValue"]
    schemas = app.openapi()["components"]["schemas"]
    referenced = {
        "Projected12MonthCustomerValue",
        "ProjectedCustomerValue",
        "ProjectedCustomerValueCohort",
    }
    for name in referenced:
        properties = schemas[name]["properties"]
        for field, definition in properties.items():
            if field.endswith("_estimate"):
                assert definition["description"].startswith("Estimate:")
    assert "projected_12_month_customer_value" in schemas["CustomersResponse"]["properties"]
    assert schema["properties"]["value"]["anyOf"]
