from datetime import UTC, datetime

import pytest
from app.auth import get_now
from app.config import Settings, get_settings
from app.main import app
from app.tokens import new_token
from fastapi.testclient import TestClient

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
ROWS = [
    "before,2025-01-01,p/one,Slash Product,2,10.00",
    "before-2,2025-01-03,p-two,Second Product,1,5.00",
    "current,2025-01-08,p/one,Slash Product,1,20.00",
    "current-2,2025-01-10,p-two,Second Product,2,5.00",
    "current-3,2025-01-14,p-two,Second Product,1,0.00",
]


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: datetime(2025, 1, 20, tzinfo=UTC)
    yield TestClient(app)
    app.dependency_overrides.clear()


def create(client, rows=ROWS, currency="EUR"):
    csv = HEADER + "\n" + "\n".join(rows) + "\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("x.csv", csv.encode(), "text/csv")},
        data={"currency": currency},
    )
    assert response.status_code == 201
    return response.json()


def request(client, path, dataset, **params):
    return client.get(
        f"/api/datasets/{dataset['dataset_id']}{path}",
        params=params,
        headers={"Authorization": f"Bearer {dataset['token']}"},
    )


def test_overview_has_compared_kpis_and_same_granularity_comparison_trend(client):
    dataset = create(client)
    response = request(
        client,
        "/overview",
        dataset,
        start="2025-01-08",
        end="2025-01-14",
        comparison="previous_period",
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "range",
        "currency",
        "granularity",
        "comparison",
        "kpis",
        "trend",
        "comparison_trend",
        "top_products",
    }
    assert body["range"] == {"start": "2025-01-08", "end": "2025-01-14"}
    assert body["comparison"] == {
        "mode": "previous_period",
        "current": {"start": "2025-01-08", "end": "2025-01-14"},
        "comparison": {"start": "2025-01-01", "end": "2025-01-07"},
        "state": "available",
        "reason": None,
    }
    assert body["kpis"] == {
        "gross_sales": {
            "value": "30.0000",
            "comparison_value": "25.0000",
            "absolute_change": "5.0000",
            "percent_change": "20.00",
            "change_status": "comparable",
        },
        "orders": {
            "value": 3,
            "comparison_value": 2,
            "absolute_change": 1,
            "percent_change": "50.00",
            "change_status": "comparable",
        },
        "units_sold": {
            "value": 4,
            "comparison_value": 3,
            "absolute_change": 1,
            "percent_change": "33.33",
            "change_status": "comparable",
        },
        "average_order_value": {
            "value": "10.0000",
            "comparison_value": "12.5000",
            "absolute_change": "-2.5000",
            "percent_change": "-20.00",
            "change_status": "comparable",
        },
    }
    assert body["granularity"] == "daily"
    assert len(body["trend"]) == len(body["comparison_trend"]) == 7
    assert body["top_products"][0]["product_id"] == "p/one"


def test_overview_unavailable_comparison_keeps_current_values_and_nulls_baseline(client):
    dataset = create(client)
    body = request(client, "/overview", dataset).json()

    assert body["comparison"]["state"] == "unavailable"
    assert body["comparison"]["reason"]
    assert body["comparison_trend"] is None
    assert body["kpis"]["gross_sales"]["value"] == "55.0000"
    assert body["kpis"]["gross_sales"]["comparison_value"] is None
    assert body["kpis"]["gross_sales"]["change_status"] is None


def test_products_and_detail_support_zero_result_and_slash_ids(client):
    dataset = create(client)
    products = request(
        client,
        "/products",
        dataset,
        start="2025-01-06",
        end="2025-01-07",
    )
    assert products.status_code == 200
    assert products.json()["product_count"] == 0
    assert products.json()["availability"]["state"] == "zero_result"
    assert products.json()["rankings"]["availability"]["state"] == "zero_result"
    assert products.json()["share"]["availability"]["state"] == "zero_result"
    assert products.json()["growth"]["availability"]["state"] == "zero_result"

    detail = request(
        client,
        "/products/detail",
        dataset,
        product_id="p/one",
        start="2025-01-06",
        end="2025-01-07",
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["product"] == {"product_id": "p/one", "product_name": "Slash Product"}
    assert body["availability"]["state"] == "zero_result"
    assert body["kpis"]["gross_sales"]["value"] == "0.0000"
    assert body["kpis"]["gross_sales"]["change_status"] == "no_change"
    assert all(bucket["gross_sales"] == "0.0000" for bucket in body["trend"])


def test_products_response_contains_three_top_ten_rankings(client):
    dataset = create(client)
    response = request(client, "/products", dataset, start="2025-01-01", end="2025-01-14")

    assert response.status_code == 200
    rankings = response.json()["rankings"]
    assert rankings["availability"] == {"state": "available", "reason": None}
    assert [row["product_id"] for row in rankings["by_gross_sales"]] == ["p/one", "p-two"]
    assert [row["product_id"] for row in rankings["by_units_sold"]] == ["p-two", "p/one"]
    assert [row["product_id"] for row in rankings["by_orders"]] == ["p-two", "p/one"]
    assert rankings["by_gross_sales"][0]["gross_sales"] == "40.0000"
    assert isinstance(rankings["by_gross_sales"][0]["units_sold"], int)

    share = response.json()["share"]
    assert share["product_count"] == 2
    assert share["total_gross_sales"] == "55.0000"
    assert share["top_20_percent_product_count"] == 1
    assert share["top_20_percent_share"] == "0.727273"
    assert share["products_to_80_percent"] == 2
    assert share["products"][0]["gross_sales_share"] == "0.727273"
    assert share["products"][-1]["cumulative_share"] == "1.000000"

    growth = response.json()["growth"]
    assert growth["availability"] == {"state": "available", "reason": None}
    assert [row["product_id"] for row in growth["products"]] == ["p-two", "p/one"]
    assert growth["products"][0]["gross_sales"] == {
        "value": "15.0000",
        "comparison_value": None,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }
    assert growth["products"][0]["classification"] is None


def test_products_dormancy_uses_anchor_and_cache_option(client):
    dataset = create(
        client,
        [
            "old,2024-01-01,old,Old Product,1,5.00",
            "boundary,2024-02-01,boundary,Boundary Product,1,8.00",
            "current,2024-03-31,current,Current Product,1,2.00",
        ],
    )
    default = request(client, "/products", dataset)
    assert default.status_code == 200
    assert default.json()["dormant"]["window_days"] == 60
    assert default.json()["dormant"]["anchor_date"] == "2024-03-31"
    assert [row["product_id"] for row in default.json()["dormant"]["products"]] == ["old"]

    thirty = request(client, "/products", dataset, dormancy_days="30")
    assert thirty.json()["dormant"]["window_days"] == 30
    assert [row["product_id"] for row in thirty.json()["dormant"]["products"]] == [
        "boundary",
        "old",
    ]
    repeated = request(client, "/products", dataset, dormancy_days="30")
    assert repeated.json() == thirty.json()


@pytest.mark.parametrize("value", ["0", "45", "-60", "120", "abc", ""])
def test_products_rejects_invalid_dormancy_days(client, value):
    dataset = create(client)
    response = request(client, "/products", dataset, dormancy_days=value)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "dormancy_days must be 30, 60 or 90.",
        }
    }


def test_detail_comparison_and_malicious_unknown_id_are_safe(client, capsys):
    dataset = create(client)
    detail = request(
        client,
        "/products/detail",
        dataset,
        product_id="p/one",
        start="2025-01-08",
        end="2025-01-14",
    )
    assert detail.status_code == 200
    assert detail.json()["kpis"]["gross_sales"]["value"] == "20.0000"

    malicious = "missing'/;%"
    response = request(client, "/products/detail", dataset, product_id=malicious)
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "product_not_found",
            "message": "The product was not found in this dataset.",
        }
    }
    assert malicious not in capsys.readouterr().err


@pytest.mark.parametrize("path", ["/overview", "/products", "/products/detail"])
@pytest.mark.parametrize(
    "params",
    [
        {"start": "2025-01-10", "end": "2025-01-09"},
        {"start": "2024-12-31"},
        {"start": "2025-01-02T00:00:00"},
    ],
)
def test_module_endpoints_reject_bad_ranges(client, path, params):
    dataset = create(client)
    if path.endswith("detail"):
        params = {**params, "product_id": "p/one"}
    response = request(client, path, dataset, **params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_range"


@pytest.mark.parametrize("path", ["/overview", "/products", "/products/detail"])
def test_unknown_comparison_is_not_echoed(client, path):
    dataset = create(client)
    params = {"comparison": "secret-mode"}
    if path.endswith("detail"):
        params["product_id"] = "p/one"
    response = request(client, path, dataset, **params)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "comparison must be previous_period or previous_year.",
        }
    }
    assert "secret-mode" not in response.text


def test_missing_and_empty_product_id_are_invalid(client):
    dataset = create(client)
    for params in ({}, {"product_id": ""}):
        response = request(client, "/products/detail", dataset, **params)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"


def test_bad_token_wins_over_bad_module_options(client):
    dataset = create(client)
    response = client.get(
        f"/api/datasets/{dataset['dataset_id']}/overview?start=bad&comparison=bad",
        headers={"Authorization": f"Bearer {new_token()}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_module_endpoints_are_documented_with_typed_responses():
    paths = app.openapi()["paths"]
    schemas = app.openapi()["components"]["schemas"]
    assert "/api/datasets/{id}/overview" in paths
    assert "/api/datasets/{id}/products" in paths
    assert "/api/datasets/{id}/products/detail" in paths
    assert "OverviewResponse" in schemas
    assert "ProductsResponse" in schemas
    assert "ProductDetailResponse" in schemas
    assert "rankings" in schemas["ProductsResponse"]["properties"]
    assert "share" in schemas["ProductsResponse"]["properties"]
    assert "growth" in schemas["ProductsResponse"]["properties"]
    assert "dormant" in schemas["ProductsResponse"]["properties"]
    assert "dormancy_days" in {
        parameter["name"]
        for parameter in paths["/api/datasets/{id}/products"]["get"]["parameters"]
    }
    comparison = schemas["ComparisonResponse"]["properties"]["mode"]
    assert comparison["enum"] == ["previous_period", "previous_year"]
