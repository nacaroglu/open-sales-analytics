import inspect
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.api.datasets as datasets_module
from app.auth import get_now, require_dataset
from app.config import Settings, get_settings
from app.main import app
from app.tokens import new_dataset_id, new_token

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
ROWS = ["o1,2025-01-02,p1,Mug,2,19.99", "o2,2025-01-10,p2,Cup,1,4.50"]


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)


@pytest.fixture
def now():
    return {"value": datetime.now(UTC)}


@pytest.fixture
def client(settings, now):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: now["value"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def create(client):
    csv = HEADER + "\n" + "\n".join(ROWS) + "\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("x.csv", csv.encode(), "text/csv")},
        data={"currency": "EUR"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def dataset(client):
    return create(client)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def remove(client, dataset_id, token=None):
    return client.delete(f"/api/datasets/{dataset_id}", headers=auth(token) if token else {})


def files(settings):
    return sorted(p.name for p in settings.dataset_dir.iterdir())


def test_authorised_delete_returns_204_with_empty_body(client, dataset):
    response = remove(client, dataset["dataset_id"], dataset["token"])
    assert response.status_code == 204
    assert response.content == b""


def test_delete_leaves_no_file_starting_with_the_id(client, settings, dataset):
    dataset_id = dataset["dataset_id"]
    (settings.dataset_dir / f"{dataset_id}.duckdb.wal").write_bytes(b"wal")
    assert remove(client, dataset_id, dataset["token"]).status_code == 204
    assert [n for n in files(settings) if n.startswith(dataset_id)] == []


def test_deleted_dataset_is_404_on_get_and_analytics(client, dataset):
    dataset_id, token = dataset["dataset_id"], dataset["token"]
    remove(client, dataset_id, token)
    for path in (f"/api/datasets/{dataset_id}", f"/api/datasets/{dataset_id}/analytics"):
        response = client.get(path, headers=auth(token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_second_delete_is_404_not_500(client, dataset):
    dataset_id, token = dataset["dataset_id"], dataset["token"]
    assert remove(client, dataset_id, token).status_code == 204
    response = remove(client, dataset_id, token)
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "The dataset was not found."}}


def test_no_token_is_401_and_file_stays(client, settings, dataset):
    before = files(settings)
    response = remove(client, dataset["dataset_id"])
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert files(settings) == before


def test_wrong_token_is_401_and_file_stays(client, settings, dataset):
    before = files(settings)
    response = remove(client, dataset["dataset_id"], new_token())
    assert response.status_code == 401
    assert files(settings) == before


def test_other_datasets_token_is_401_and_nothing_is_removed(client, settings, dataset):
    other = create(client)
    before = files(settings)
    response = remove(client, dataset["dataset_id"], other["token"])
    assert response.status_code == 401
    assert files(settings) == before
    assert client.get(f"/api/datasets/{other['dataset_id']}", headers=auth(other["token"])).status_code == 200


def test_unknown_id_is_404(client):
    response = remove(client, new_dataset_id(), new_token())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_expired_dataset_is_404_and_file_is_not_touched(client, settings, dataset, now):
    now["value"] = now["value"] + timedelta(hours=25)
    before = files(settings)
    response = remove(client, dataset["dataset_id"], dataset["token"])
    assert response.status_code == 404
    assert files(settings) == before


@pytest.mark.parametrize("bad_id", ["..%2F..%2Fx", "a" * 21, "..", "sample", "%2E%2E%2Fsecret"])
def test_malformed_id_is_404_and_removes_nothing(client, settings, dataset, bad_id):
    (settings.dataset_dir.parent / "x.duckdb").write_bytes(b"outside")
    before = files(settings)
    response = client.delete(f"/api/datasets/{bad_id}", headers=auth(dataset["token"]))
    assert response.status_code == 404
    assert files(settings) == before
    assert (settings.dataset_dir.parent / "x.duckdb").exists()


def test_file_removed_after_authorisation_is_404_not_500(client, settings, dataset):
    def authorise_then_lose_the_file(*args, **kwargs):
        result = require_dataset(*args, **kwargs)
        datasets_module.dataset_path(settings, result.id).unlink()
        return result

    app.dependency_overrides[require_dataset] = authorise_then_lose_the_file
    # FastAPI reads the wrapper's signature, so keep the original one.
    authorise_then_lose_the_file.__signature__ = inspect.signature(require_dataset)
    response = remove(client, dataset["dataset_id"], dataset["token"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_leaves_other_datasets_and_files_untouched(client, settings, dataset):
    other = create(client)
    stray = settings.dataset_dir / "notes.txt"
    stray.write_text("keep")
    other_before = (settings.dataset_dir / f"{other['dataset_id']}.duckdb").read_bytes()
    assert remove(client, dataset["dataset_id"], dataset["token"]).status_code == 204
    assert stray.read_text() == "keep"
    assert (settings.dataset_dir / f"{other['dataset_id']}.duckdb").read_bytes() == other_before
    assert client.get(f"/api/datasets/{other['dataset_id']}", headers=auth(other["token"])).status_code == 200
