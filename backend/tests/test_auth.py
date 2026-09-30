from datetime import UTC, datetime, timedelta

import app.auth as auth
import pytest
from app.auth import AuthorizedDataset, get_now, require_dataset
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.importer import dataset_path, import_dataset
from app.tokens import hash_token, new_dataset_id, new_token
from app.validation import stage_csv
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
CREATED = datetime(2025, 6, 1, 12, 30, tzinfo=UTC)
TTL = timedelta(hours=24)
EXPIRES = CREATED + TTL
NOT_FOUND = {"error": {"code": "not_found", "message": "The dataset was not found."}}


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)


@pytest.fixture
def now():
    return {"value": CREATED + timedelta(hours=1)}


@pytest.fixture
def client(settings, now):
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/datasets/{id}/whoami")
    def whoami(dataset: AuthorizedDataset = Depends(require_dataset)):
        return {"id": dataset.id, "meta": dataset.meta}

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: now["value"]
    return TestClient(app)


@pytest.fixture
def dataset(settings, tmp_path):
    token = new_token()
    dataset_id = new_dataset_id()
    csv_path = tmp_path / "in.csv"
    csv_path.write_text(HEADER + "\no1,2025-01-02,p1,Mug,2,19.99\n", encoding="utf-8")
    import_dataset(
        stage_csv(csv_path), csv_path, dataset_id, "USD", hash_token(token), settings, CREATED
    )
    return dataset_id, token


def get(client, dataset_id, authorization=None, **kwargs):
    headers = {} if authorization is None else {"Authorization": authorization.encode("latin-1")}
    return client.get(f"/datasets/{dataset_id}/whoami", headers=headers, **kwargs)


def assert_unauthorized(response):
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorized", "message": "A valid bearer token is required."}
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


def assert_not_found(response):
    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert "WWW-Authenticate" not in response.headers


def test_accepts_correct_token_and_returns_id_and_meta(client, dataset):
    dataset_id, token = dataset
    response = get(client, dataset_id, f"Bearer {token}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == dataset_id
    assert body["meta"]["id"] == dataset_id
    assert body["meta"]["currency"] == "USD"
    assert body["meta"]["expires_at"] == "2025-06-02T12:30:00Z"
    assert body["meta"]["row_count"] == 1
    assert "token_hash" not in body["meta"]


def test_scheme_is_case_insensitive(client, dataset):
    dataset_id, token = dataset
    for scheme in ("bearer", "BEARER", "bEaReR"):
        assert get(client, dataset_id, f"{scheme} {token}").status_code == 200


def test_no_authorization_header_is_401(client, dataset):
    assert_unauthorized(get(client, dataset[0]))


@pytest.mark.parametrize(
    "header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer ", "Bearer    ", "", "Token abc", "abc"]
)
def test_malformed_header_is_401(client, dataset, header):
    assert_unauthorized(get(client, dataset[0], header))


def test_unknown_dataset_is_404(client):
    assert_not_found(get(client, new_dataset_id(), f"Bearer {new_token()}"))


@pytest.mark.parametrize("bad_id", ["short", "a" * 23, "a" * 21 + ".", "a" * 21 + "%20"])
def test_malformed_id_is_404_without_touching_the_filesystem(client, monkeypatch, bad_id):
    def boom(*args, **kwargs):
        raise AssertionError("filesystem touched")

    monkeypatch.setattr(auth, "dataset_path", boom)
    monkeypatch.setattr(auth, "open_dataset_readonly", boom)
    assert_not_found(get(client, bad_id, f"Bearer {new_token()}"))


def test_expired_dataset_is_404_even_with_correct_token(client, dataset, now):
    dataset_id, token = dataset
    now["value"] = EXPIRES
    assert_not_found(get(client, dataset_id, f"Bearer {token}"))
    now["value"] = EXPIRES + timedelta(days=30)
    assert_not_found(get(client, dataset_id, f"Bearer {token}"))


def test_one_second_before_expiry_is_accepted(client, dataset, now):
    dataset_id, token = dataset
    now["value"] = EXPIRES - timedelta(seconds=1)
    assert get(client, dataset_id, f"Bearer {token}").status_code == 200


def test_wrong_token_is_401(client, dataset):
    assert_unauthorized(get(client, dataset[0], f"Bearer {new_token()}"))


def test_non_ascii_token_is_401(client, dataset):
    assert_unauthorized(get(client, dataset[0], "Bearer t\u00f6k\u00e9n"))


def test_corrupt_file_is_404(client, settings):
    dataset_id = new_dataset_id()
    settings.dataset_dir.mkdir(parents=True)
    dataset_path(settings, dataset_id).write_bytes(b"this is not a duckdb file" * 100)
    assert_not_found(get(client, dataset_id, f"Bearer {new_token()}"))


def test_file_without_meta_row_is_404(client, dataset, settings):
    import duckdb

    dataset_id, token = dataset
    connection = duckdb.connect(str(dataset_path(settings, dataset_id)))
    connection.execute("DELETE FROM dataset_meta")
    connection.close()
    assert_not_found(get(client, dataset_id, f"Bearer {token}"))


def test_file_without_meta_table_is_404(client, settings):
    import duckdb

    dataset_id = new_dataset_id()
    settings.dataset_dir.mkdir(parents=True)
    connection = duckdb.connect(str(dataset_path(settings, dataset_id)))
    connection.execute("CREATE TABLE other (x INTEGER)")
    connection.close()
    assert_not_found(get(client, dataset_id, f"Bearer {new_token()}"))


def test_check_order_header_then_existence_then_token(client, dataset, now):
    dataset_id, token = dataset
    # a bad header beats a missing dataset
    assert_unauthorized(get(client, new_dataset_id()))
    assert_unauthorized(get(client, "short", "Basic x"))
    # a missing/expired dataset beats a wrong token
    assert_not_found(get(client, new_dataset_id(), f"Bearer {new_token()}"))
    now["value"] = EXPIRES
    assert_not_found(get(client, dataset_id, f"Bearer {new_token()}"))


def test_token_is_not_accepted_from_query_or_cookie(client, dataset):
    dataset_id, token = dataset
    assert_unauthorized(get(client, dataset_id, params={"token": token, "access_token": token}))
    client.cookies.set("token", token)
    client.cookies.set("Authorization", f"Bearer {token}")
    assert_unauthorized(get(client, dataset_id))


def test_default_now_is_current_utc_time():
    assert abs(get_now() - datetime.now(UTC)) < timedelta(seconds=5)
    assert get_now().tzinfo is not None


def test_dependency_closes_its_connection(client, dataset, settings):
    import duckdb

    dataset_id, token = dataset
    assert get(client, dataset_id, f"Bearer {token}").status_code == 200
    # a read-write open fails if a read-only connection is still held in-process
    duckdb.connect(str(dataset_path(settings, dataset_id))).close()
