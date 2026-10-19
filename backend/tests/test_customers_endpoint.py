import json
from datetime import UTC, datetime

import pytest
from app.auth import get_now
from app.config import Settings, get_settings
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from fastapi.testclient import TestClient

REQUIRED = "order_id,order_date,product_id,product_name,quantity,unit_price"
CUSTOMER_HEADER = REQUIRED + ",customer_id"
NOW = datetime(2025, 1, 20, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)


@pytest.fixture
def client(settings):
    cache = ResponseCache(max_entries=20, ttl_seconds=300)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_response_cache] = lambda: cache
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(client, rows, header=CUSTOMER_HEADER):
    csv = header + "\n" + "\n".join(rows) + "\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("customers.csv", csv.encode(), "text/csv")},
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


def test_customers_returns_typed_aggregate_envelope_and_range_coverage(client):
    dataset = upload(
        client,
        [
            "o1,2025-01-01,p1,Mug,1,2.00,CUSTMARKER-0001",
            "o2,2025-01-02,p1,Mug,1,3.00,CUSTMARKER-0002",
            "o3,2025-01-03,p1,Mug,1,4.00,",
            "o4,2025-01-04,p1,Mug,1,5.00,CUSTMARKER-0004",
        ],
    )
    response = get_customers(client, dataset, start="2025-01-02", end="2025-01-03")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["module"] == "customers"
    assert body["currency"] == "EUR"
    assert body["availability"] == {
        "tier": "warning",
        "state": "available",
        "reason": None,
        "warning": {
            "state": "low_coverage",
            "reason": "Only 3 of 4 orders (75%) have a customer_id; customer results describe those orders only.",
        },
    }
    assert body["coverage"] == {
        "dataset": {
            "tier": "warning",
            "coverage": 0.75,
            "identified_orders": 3,
            "unidentified_orders": 1,
            "total_orders": 4,
        },
        "range": {
            "tier": "warning",
            "coverage": 0.5,
            "identified_orders": 1,
            "unidentified_orders": 1,
            "total_orders": 2,
        },
    }
    assert body["sections"] == {}
    body_text = response.text
    assert all(marker not in body_text for marker in ("CUSTMARKER-0001", "CUSTMARKER-0002"))


def test_customers_default_and_comparison_are_shared_with_other_modules(client):
    dataset = upload(
        client,
        [
            "o1,2024-01-01,p1,Mug,1,2.00,CUST-1",
            "o2,2025-01-01,p1,Mug,1,3.00,CUST-2",
        ],
    )
    response = get_customers(client, dataset, comparison="previous_year")

    assert response.status_code == 200
    assert response.json()["comparison"] == {
        "mode": "previous_year",
        "current": {"start": "2024-01-01", "end": "2025-01-01"},
        "comparison": {"start": "2023-01-01", "end": "2024-01-01"},
        "state": "unavailable",
        "reason": "The comparison needs data from 2023-01-01, but the dataset starts on 2024-01-01.",
    }


@pytest.mark.parametrize(
    ("header", "rows", "tier", "state"),
    [
        (REQUIRED, ["o1,2025-01-01,p1,Mug,1,2.00"], "missing", "unavailable"),
        (
            CUSTOMER_HEADER,
            [
                "o1,2025-01-01,p1,Mug,1,2.00,CUST-1",
                "o2,2025-01-02,p1,Mug,1,2.00,",
                "o3,2025-01-03,p1,Mug,1,2.00,",
            ],
            "suppressed",
            "low_coverage",
        ),
        (
            CUSTOMER_HEADER,
            [
                "o1,2025-01-01,p1,Mug,1,2.00,CUST-1",
                "o2,2025-01-02,p1,Mug,1,2.00,CUST-2",
                "o3,2025-01-03,p1,Mug,1,2.00,",
            ],
            "warning",
            "available",
        ),
        (
            CUSTOMER_HEADER,
            [
                "o1,2025-01-01,p1,Mug,1,2.00,CUST-1",
                "o2,2025-01-02,p1,Mug,1,2.00,CUST-2",
                "o3,2025-01-03,p1,Mug,1,2.00,CUST-3",
            ],
            "normal",
            "available",
        ),
    ],
)
def test_customer_availability_tiers_are_200_states(client, header, rows, tier, state):
    dataset = upload(client, rows, header)
    response = get_customers(client, dataset)

    assert response.status_code == 200
    body = response.json()
    assert body["availability"]["tier"] == tier
    assert body["availability"]["state"] == state
    assert body["sections"] == {}


@pytest.mark.parametrize(
    "params",
    [
        {"start": "not-a-date"},
        {"start": "2025-01-03", "end": "2025-01-01"},
        {"start": "2024-01-01"},
    ],
)
def test_customers_uses_shared_invalid_range_errors(client, params):
    dataset = upload(client, ["o1,2025-01-01,p1,Mug,1,2.00,CUST-1"])
    response = get_customers(client, dataset, **params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_range"


def test_customers_auth_and_method_rules(client):
    dataset = upload(client, ["o1,2025-01-01,p1,Mug,1,2.00,CUST-1"])
    path = f"/api/datasets/{dataset['dataset_id']}/customers"
    missing = client.get(path)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert client.get(path, headers={"Authorization": "Basic wrong"}).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.post(path, headers={"Authorization": f"Bearer {dataset['token']}"}).status_code
        == 405
    )
    assert (
        client.get(
            path + "/anything", headers={"Authorization": f"Bearer {dataset['token']}"}
        ).status_code
        == 404
    )


def test_customers_openapi_is_aggregate_only_and_route_is_unique(client):
    schema = client.get("/openapi.json").json()
    customer_schema = schema["paths"]["/api/datasets/{id}/customers"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert customer_schema["$ref"].endswith("CustomersResponse")
    serialized = json.dumps(schema["components"]["schemas"]["CustomersResponse"])
    assert "customer_id" not in serialized
    assert "customer_ids" not in serialized
    assert [path for path in schema["paths"] if "customer" in path] == [
        "/api/datasets/{id}/customers"
    ]
