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


def test_customers_returns_typed_aggregate_envelope_and_range_coverage(client, capsys):
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
    assert body["sections"]["identified_customers"] == {
        "availability": {"state": "available", "reason": None},
        "value": {
            "value": 1,
            "comparison_value": None,
            "absolute_change": None,
            "percent_change": None,
            "change_status": None,
        },
    }
    unavailable_comparison = {
        "comparison_value": None,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }
    assert body["sections"]["new_vs_returning"] == {
        "availability": {"state": "available", "reason": None},
        "new_customer_gross_sales": {"value": "3.0000", **unavailable_comparison},
        "returning_customer_gross_sales": {"value": "0.0000", **unavailable_comparison},
        "identified_gross_sales": {"value": "3.0000", **unavailable_comparison},
    }
    markers = ("CUSTMARKER-0001", "CUSTMARKER-0002", "CUSTMARKER-0004")
    body_text = response.text
    assert all(marker not in body_text for marker in markers)
    captured = capsys.readouterr()
    log_text = captured.out + captured.err
    assert all(marker not in log_text for marker in markers)


def test_identified_customers_comparison_uses_shared_change_semantics(client):
    dataset = upload(
        client,
        [
            "o1,2026-02-28,p1,Mug,1,2.00,C1",
            "o2,2026-03-01,p1,Mug,1,2.00,C1",
            "o3,2026-03-15,p1,Mug,1,2.00,C2",
        ],
    )
    response = get_customers(client, dataset, start="2026-03-01", end="2026-03-01")
    value = response.json()["sections"]["identified_customers"]["value"]
    assert value == {
        "value": 1,
        "comparison_value": 1,
        "absolute_change": 0,
        "percent_change": "0.00",
        "change_status": "comparable",
    }


def test_identified_customers_zero_result_is_available_as_a_section(client):
    dataset = upload(
        client,
        ["o1,2025-01-01,p1,Mug,1,2.00,C1", "o2,2025-01-03,p1,Mug,1,2.00,C2"],
    )
    response = get_customers(client, dataset, start="2025-01-02", end="2025-01-02")
    section = response.json()["sections"]["identified_customers"]
    assert section["availability"]["state"] == "zero_result"
    assert section["value"]["value"] == 0


GOLDEN_ROWS = [
    "a1,2026-01-10,p1,Mug,1,100.00,A",
    "a2,2026-01-10,p2,Cup,1,50.00,A",
    "a3,2026-02-05,p1,Mug,1,30.00,A",
    "b1,2026-02-05,p1,Mug,1,20.00,B",
    "b2,2026-02-20,p1,Mug,1,40.00,B",
    "u1,2026-02-10,p1,Mug,1,999.00,",
]


def test_new_vs_returning_comparison_classifies_by_first_order_date(client):
    dataset = upload(client, GOLDEN_ROWS)
    body = get_customers(client, dataset, start="2026-02-06", end="2026-02-20").json()

    assert body["comparison"]["comparison"] == {"start": "2026-01-22", "end": "2026-02-05"}
    assert body["sections"]["new_vs_returning"] == {
        "availability": {"state": "available", "reason": None},
        "new_customer_gross_sales": {
            "value": "0.0000",
            "comparison_value": "20.0000",
            "absolute_change": "-20.0000",
            "percent_change": "-100.00",
            "change_status": "comparable",
        },
        "returning_customer_gross_sales": {
            "value": "40.0000",
            "comparison_value": "30.0000",
            "absolute_change": "10.0000",
            "percent_change": "33.33",
            "change_status": "comparable",
        },
        "identified_gross_sales": {
            "value": "40.0000",
            "comparison_value": "50.0000",
            "absolute_change": "-10.0000",
            "percent_change": "-20.00",
            "change_status": "comparable",
        },
    }


def test_new_vs_returning_empty_comparison_period_has_no_prior_value(client):
    dataset = upload(client, GOLDEN_ROWS)
    body = get_customers(client, dataset, start="2026-02-01", end="2026-02-20").json()

    assert body["comparison"]["comparison"] == {"start": "2026-01-12", "end": "2026-01-31"}
    section = body["sections"]["new_vs_returning"]
    for key, value in (
        ("new_customer_gross_sales", "20.0000"),
        ("returning_customer_gross_sales", "70.0000"),
        ("identified_gross_sales", "90.0000"),
    ):
        assert section[key]["value"] == value
        assert section[key]["comparison_value"] == "0.0000"
        assert section[key]["change_status"] == "no_prior_value"
        assert section[key]["percent_change"] is None


def test_new_vs_returning_unavailable_comparison_is_not_queried(client, monkeypatch):
    import app.api.customers as customers_api

    calls = []
    original = customers_api.read_new_vs_returning

    def recording(connection, start, end):
        calls.append((start.isoformat(), end.isoformat()))
        return original(connection, start, end)

    monkeypatch.setattr(customers_api, "read_new_vs_returning", recording)
    dataset = upload(client, GOLDEN_ROWS)
    body = get_customers(client, dataset, start="2026-01-11", end="2026-02-20").json()

    assert body["comparison"]["state"] == "unavailable"
    assert calls == [("2026-01-11", "2026-02-20")]
    section = body["sections"]["new_vs_returning"]
    for key, value in (
        ("new_customer_gross_sales", "20.0000"),
        ("returning_customer_gross_sales", "70.0000"),
        ("identified_gross_sales", "90.0000"),
    ):
        assert section[key] == {
            "value": value,
            "comparison_value": None,
            "absolute_change": None,
            "percent_change": None,
            "change_status": None,
        }


def test_new_vs_returning_zero_result(client):
    dataset = upload(
        client,
        [
            "a1,2025-01-10,p1,Mug,1,100.00,C1",
            "a2,2025-02-05,p1,Mug,1,30.00,C1",
            "u1,2025-01-20,p1,Mug,1,9.00,",
        ],
    )
    body = get_customers(client, dataset, start="2025-01-11", end="2025-01-31").json()
    section = body["sections"]["new_vs_returning"]

    assert section["availability"] == {
        "state": "zero_result",
        "reason": "No identified customer rows were found in the selected range.",
    }
    for key in (
        "new_customer_gross_sales",
        "returning_customer_gross_sales",
        "identified_gross_sales",
    ):
        assert section[key]["value"] == "0.0000"


def test_missing_and_suppressed_coverage_omit_identified_customer_section(client, monkeypatch):
    import app.api.customers as customers_api

    def not_run(*args):
        raise AssertionError("new_vs_returning must not be queried")

    monkeypatch.setattr(customers_api, "read_new_vs_returning", not_run)
    missing = upload(client, ["o1,2025-01-01,p1,Mug,1,2.00"], REQUIRED)
    assert get_customers(client, missing).json()["sections"] == {}
    suppressed = upload(
        client,
        [
            "o1,2025-01-01,p1,Mug,1,2.00,C1",
            "o2,2025-01-02,p1,Mug,1,2.00,",
            "o3,2025-01-03,p1,Mug,1,2.00,",
        ],
    )
    assert get_customers(client, suppressed).json()["sections"] == {}


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
    if tier in {"missing", "suppressed"}:
        assert body["sections"] == {}
    else:
        assert body["sections"]["identified_customers"]["value"]["value"] == (
            2 if tier == "warning" else 3
        )
        section = body["sections"]["new_vs_returning"]
        assert section["availability"] == {"state": "available", "reason": None}
        identified_sales = "4.0000" if tier == "warning" else "6.0000"
        assert section["new_customer_gross_sales"]["value"] == identified_sales
        assert section["returning_customer_gross_sales"]["value"] == "0.0000"
        assert section["identified_gross_sales"]["value"] == identified_sales
    if tier in {"missing", "suppressed"}:
        assert "new_vs_returning" not in body["sections"]


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
    assert "NewVsReturningSection" in json.dumps(schema["components"]["schemas"])
    assert [path for path in schema["paths"] if "customer" in path] == [
        "/api/datasets/{id}/customers"
    ]
