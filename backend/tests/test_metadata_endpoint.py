from datetime import UTC, datetime, timedelta

import pytest
from app.auth import get_now
from app.config import Settings, get_settings
from app.importer import import_dataset
from app.main import app
from app.tokens import hash_token, new_dataset_id, new_token
from app.validation import stage_csv
from fastapi.testclient import TestClient

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
CREATED = datetime(2025, 6, 1, 12, 30, tzinfo=UTC)
KEYS = {"id", "currency", "created_at", "expires_at", "row_count", "date_range"}


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)


@pytest.fixture
def now():
    return {"value": CREATED + timedelta(hours=1)}


@pytest.fixture
def client(settings, now):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: now["value"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_dataset(settings, tmp_path):
    def make(rows):
        token, dataset_id = new_token(), new_dataset_id()
        csv_path = tmp_path / f"{dataset_id}.csv"
        csv_path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        import_dataset(
            stage_csv(csv_path), csv_path, dataset_id, "EUR", hash_token(token), settings, CREATED
        )
        return dataset_id, token

    return make


def fetch(client, dataset_id, token):
    return client.get(f"/api/datasets/{dataset_id}", headers={"Authorization": f"Bearer {token}"})


def test_returns_metadata_with_exactly_the_documented_keys(client, make_dataset):
    dataset_id, token = make_dataset(
        ["o1,2025-01-02,p1,Mug,2,19.99", "o2,2025-03-09,p2,Cup,1,5.00"]
    )
    response = fetch(client, dataset_id, token)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "id": dataset_id,
        "currency": "EUR",
        "created_at": "2025-06-01T12:30:00Z",
        "expires_at": "2025-06-02T12:30:00Z",
        "row_count": 2,
        "date_range": {"min": "2025-01-02", "max": "2025-03-09"},
    }
    assert set(response.json()) == KEYS
    assert isinstance(response.json()["row_count"], int)


def test_single_date_dataset_has_equal_min_and_max(client, make_dataset):
    dataset_id, token = make_dataset(
        ["o1,2025-02-02,p1,Mug,2,19.99", "o2,2025-02-02,p2,Cup,1,5.00"]
    )
    date_range = fetch(client, dataset_id, token).json()["date_range"]
    assert date_range == {"min": "2025-02-02", "max": "2025-02-02"}


def test_body_leaks_no_token_hash_or_path(client, make_dataset, settings):
    dataset_id, token = make_dataset(["o1,2025-01-02,p1,Mug,2,19.99"])
    text = fetch(client, dataset_id, token).text
    assert token not in text
    assert hash_token(token) not in text
    assert "token" not in text.lower()
    assert str(settings.dataset_dir) not in text
    assert ".duckdb" not in text


def test_matches_the_meta_returned_by_upload(client, tmp_path):
    csv = HEADER + "\no1,2025-01-02,p1,Mug,2,19.99\no2,2025-01-05,p1,Mug,1,19.99\n"
    created = client.post(
        "/api/datasets",
        files={"file": ("x.csv", csv.encode(), "text/csv")},
        data={"currency": "USD"},
    ).json()
    response = fetch(client, created["dataset_id"], created["token"])
    assert response.status_code == 200
    assert response.json() == created["meta"]


def test_missing_token_is_401(client, make_dataset):
    dataset_id, _ = make_dataset(["o1,2025-01-02,p1,Mug,2,19.99"])
    response = client.get(f"/api/datasets/{dataset_id}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_token_is_401(client, make_dataset):
    dataset_id, _ = make_dataset(["o1,2025-01-02,p1,Mug,2,19.99"])
    response = fetch(client, dataset_id, new_token())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_dataset_is_404(client):
    response = fetch(client, new_dataset_id(), new_token())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_expired_dataset_is_404_even_with_correct_token(client, make_dataset, now):
    dataset_id, token = make_dataset(["o1,2025-01-02,p1,Mug,2,19.99"])
    now["value"] = CREATED + timedelta(hours=24)
    response = fetch(client, dataset_id, token)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_post_sample_is_not_captured_by_the_id_route(client, settings):
    response = client.post("/api/datasets/sample")
    assert response.status_code == 201
    assert set(response.json()) >= {"dataset_id", "token", "meta"}
    assert len(list(settings.dataset_dir.glob("*.duckdb"))) == 1


def test_get_sample_is_a_malformed_id_not_a_dataset(client):
    # "sample" is not a valid dataset ID, so #14 answers 404 (401 without a token).
    created = client.post("/api/datasets/sample").json()
    response = client.get(
        "/api/datasets/sample", headers={"Authorization": f"Bearer {created['token']}"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert client.get("/api/datasets/sample").status_code == 401
