import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app.api.datasets as datasets_module
from app.auth import get_now
from app.config import Settings, get_settings
from app.main import app
from app.tokens import new_dataset_id, new_token

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
ROWS = [
    "o1,2025-01-02,p1,Mug,2,19.99",
    "o1,2025-01-02,p2,Cup,1,4.50",
    "o2,2025-01-10,p1,Mug,1,19.99",
    "o3,2025-01-20,p3,Bowl,3,7.25",
]
KEYS = {"range", "currency", "granularity", "kpis", "trend", "top_products"}
MONEY = re.compile(r"-?\d+\.\d{4}")


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def settings(data_dir):
    return Settings(DATASET_DIR=data_dir, DATASET_TTL_HOURS=24)


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
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


@pytest.fixture
def dataset(client):
    return create(client)


def analytics(client, dataset, query="", token=None):
    token = dataset["token"] if token is None else token
    return client.get(
        f"/api/datasets/{dataset['dataset_id']}/analytics{query}",
        headers={"Authorization": f"Bearer {token}"},
    )


def assert_invalid_range(response):
    assert response.status_code == 400
    body = response.json()
    assert list(body) == ["error"]
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "invalid_range"


# --- shape ---


def test_full_range_response(client, dataset):
    response = analytics(client, dataset)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == KEYS
    assert body["range"] == {"start": "2025-01-02", "end": "2025-01-20"}
    assert body["currency"] == "EUR"
    assert body["granularity"] == "daily"
    assert body["kpis"] == {
        "gross_sales": "86.2200",
        "orders": 3,
        "units_sold": 7,
        "average_order_value": "28.7400",
    }
    assert isinstance(body["kpis"]["orders"], int)
    assert isinstance(body["kpis"]["units_sold"], int)
    assert len(body["trend"]) == 19
    assert body["trend"][0] == {"bucket_start": "2025-01-02", "gross_sales": "44.4800"}
    assert body["trend"][1] == {"bucket_start": "2025-01-03", "gross_sales": "0.0000"}
    assert body["top_products"][0] == {
        "product_id": "p1",
        "product_name": "Mug",
        "gross_sales": "59.9700",
        "units_sold": 3,
        "distinct_orders": 2,
    }
    assert [p["product_id"] for p in body["top_products"]] == ["p1", "p3", "p2"]


def test_money_is_a_four_decimal_string_everywhere(client, dataset):
    body = analytics(client, dataset).json()
    values = [body["kpis"]["gross_sales"], body["kpis"]["average_order_value"]]
    values += [b["gross_sales"] for b in body["trend"]]
    values += [p["gross_sales"] for p in body["top_products"]]
    assert all(isinstance(v, str) and MONEY.fullmatch(v) for v in values)


def test_at_most_ten_top_products(client):
    rows = [f"o{i},2025-01-02,p{i:02d},Item {i},1,{i}.00" for i in range(1, 13)]
    body = analytics(client, create(client, rows)).json()
    assert len(body["top_products"]) == 10
    assert body["top_products"][0]["product_id"] == "p12"


# --- range ---


def test_sub_range(client, dataset):
    body = analytics(client, dataset, "?start=2025-01-10&end=2025-01-20").json()
    assert body["range"] == {"start": "2025-01-10", "end": "2025-01-20"}
    assert body["kpis"]["gross_sales"] == "41.7400"
    assert body["kpis"]["orders"] == 2
    assert len(body["trend"]) == 11


def test_only_start_defaults_end_to_last_date(client, dataset):
    body = analytics(client, dataset, "?start=2025-01-10").json()
    assert body["range"] == {"start": "2025-01-10", "end": "2025-01-20"}


def test_only_end_defaults_start_to_first_date(client, dataset):
    body = analytics(client, dataset, "?end=2025-01-10").json()
    assert body["range"] == {"start": "2025-01-02", "end": "2025-01-10"}


def test_start_equal_to_end_is_accepted(client, dataset):
    body = analytics(client, dataset, "?start=2025-01-02&end=2025-01-02").json()
    assert body["range"] == {"start": "2025-01-02", "end": "2025-01-02"}
    assert body["kpis"]["orders"] == 1
    assert body["trend"] == [{"bucket_start": "2025-01-02", "gross_sales": "44.4800"}]


def test_range_edges_of_the_dataset_are_accepted(client, dataset):
    assert analytics(client, dataset, "?start=2025-01-02&end=2025-01-20").status_code == 200


def test_range_without_sales_gives_zeros(client, dataset):
    body = analytics(client, dataset, "?start=2025-01-05&end=2025-01-08").json()
    assert body["kpis"] == {
        "gross_sales": "0.0000",
        "orders": 0,
        "units_sold": 0,
        "average_order_value": "0.0000",
    }
    assert [b["gross_sales"] for b in body["trend"]] == ["0.0000"] * 4
    assert body["top_products"] == []


@pytest.mark.parametrize(
    "query",
    [
        "?start=2025-01-10&end=2025-01-09",
        "?start=2025-01-01",
        "?end=2025-01-21",
        "?start=2025-01-02&end=2025-02-01",
        "?start=2024-12-31&end=2025-01-05",
        "?start=2025-01-21",
        "?end=2025-01-01",
        "?start=2025-1-05",
        "?start=20250105",
        "?start=2025/01/05",
        "?start=2025-01-05T00:00:00",
        "?start=%202025-01-05",
        "?start=2025-01-05%0A",
        "?start=2025-02-30",
        "?end=2025-13-01",
        "?start=",
        "?end=",
        "?start=&end=",
        "?start=abc",
        "?start=%D9%A2%D9%A0%D9%A2%D9%A5-%D9%A0%D9%A1-%D9%A0%D9%A5",
    ],
)
def test_bad_ranges_are_400_invalid_range(client, dataset, query):
    assert_invalid_range(analytics(client, dataset, query))


# --- authorisation ---


def test_no_token_is_401(client, dataset):
    response = client.get(f"/api/datasets/{dataset['dataset_id']}/analytics")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_wrong_token_is_401(client, dataset):
    response = analytics(client, dataset, token=new_token())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_dataset_is_404(client, dataset):
    response = client.get(
        f"/api/datasets/{new_dataset_id()}/analytics",
        headers={"Authorization": f"Bearer {dataset['token']}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_expired_dataset_is_404(client, dataset):
    later = datetime.now(UTC) + timedelta(hours=25)
    app.dependency_overrides[get_now] = lambda: later
    response = analytics(client, dataset)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_bad_token_wins_over_bad_range(client, dataset):
    assert analytics(client, dataset, "?start=abc", token=new_token()).status_code == 401


# --- initial_summary ---


def test_upload_initial_summary_equals_the_endpoint(client, dataset):
    summary = dataset["initial_summary"]
    assert set(summary) == KEYS
    assert summary == analytics(client, dataset).json()


def test_sample_initial_summary_equals_the_endpoint(client):
    created = client.post("/api/datasets/sample").json()
    assert created["initial_summary"] == analytics(client, created).json()


def test_summary_failure_after_upload_is_500_and_removes_the_dataset(client, data_dir, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError(f"secret {data_dir}")

    monkeypatch.setattr(datasets_module, "build_summary", boom)
    csv = HEADER + "\n" + ROWS[0] + "\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("x.csv", csv.encode(), "text/csv")},
        data={"currency": "USD"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong on the server."}
    }
    assert "secret" not in response.text
    assert not list(data_dir.glob("*.duckdb*"))
    uploads = data_dir / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_summary_failure_after_sample_is_500_internal_error_and_removes_the_dataset(
    client, data_dir, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError(f"secret {data_dir}")

    monkeypatch.setattr(datasets_module, "build_summary", boom)
    response = client.post("/api/datasets/sample")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert not list(data_dir.glob("*.duckdb*"))


# --- integration over the sample dataset ---


def test_sample_dataset_full_range_and_sub_range(client):
    created = client.post("/api/datasets/sample").json()

    full = analytics(client, created)
    assert full.status_code == 200
    body = full.json()
    assert body["range"] == {"start": "2025-01-01", "end": "2025-12-31"}
    assert body["currency"] == "USD"
    assert body["granularity"] == "weekly"
    assert sum(Decimal(b["gross_sales"]) for b in body["trend"]) == Decimal(body["kpis"]["gross_sales"])
    assert body["kpis"]["orders"] > 0
    assert 0 < len(body["top_products"]) <= 10

    sub = analytics(client, created, "?start=2025-03-01&end=2025-03-31")
    assert sub.status_code == 200
    part = sub.json()
    assert part["range"] == {"start": "2025-03-01", "end": "2025-03-31"}
    assert part["granularity"] == "daily"
    assert len(part["trend"]) == 31
    assert sum(Decimal(b["gross_sales"]) for b in part["trend"]) == Decimal(part["kpis"]["gross_sales"])
    assert Decimal(part["kpis"]["gross_sales"]) < Decimal(body["kpis"]["gross_sales"])
