import hashlib

import pytest
from fastapi.testclient import TestClient

import app.api.datasets as datasets_module
from app.config import Settings, get_settings
from app.main import app
from app.schema import open_dataset_readonly
from app.tokens import verify_token

SAMPLE = datasets_module.SAMPLE_CSV
SAMPLE_BYTES = SAMPLE.read_bytes()


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def settings(data_dir):
    return Settings(DATASET_DIR=data_dir)


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


def assert_no_leftovers(data_dir):
    """Nothing but dataset files and an empty uploads/ folder may remain."""
    assert {p for p in tree(data_dir) if not p.endswith(".duckdb")} <= {"uploads"}
    uploads = data_dir / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def assert_clean(data_dir):
    assert set(tree(data_dir)) <= {"uploads"}
    uploads = data_dir / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def line_count(dataset_file):
    connection = open_dataset_readonly(dataset_file)
    try:
        return connection.execute("SELECT count(*) FROM line_items").fetchone()[0]
    finally:
        connection.close()


def test_sample_returns_the_same_shape_as_an_upload(client):
    response = client.post("/api/datasets/sample")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"dataset_id", "token", "meta", "warnings"}
    assert body["warnings"] == []
    assert body["meta"]["id"] == body["dataset_id"]
    assert set(body["meta"]) == {"id", "currency", "created_at", "expires_at", "row_count", "date_range"}


def test_sample_meta_is_usd_with_the_full_year(client):
    meta = client.post("/api/datasets/sample").json()["meta"]

    rows = len(SAMPLE.read_text().splitlines()) - 1
    assert meta["currency"] == "USD"
    assert meta["row_count"] == rows
    assert meta["date_range"] == {"min": "2025-01-01", "max": "2025-12-31"}


def test_dataset_file_exists_token_verifies_and_rows_are_readable(client, settings):
    body = client.post("/api/datasets/sample").json()

    assert verify_token(body["dataset_id"], body["token"], settings)
    files = list(settings.dataset_dir.glob("*.duckdb"))
    assert len(files) == 1 and body["dataset_id"] in files[0].name
    assert line_count(files[0]) == body["meta"]["row_count"]


def test_bundled_file_is_untouched_and_nothing_is_left_behind(client, data_dir):
    before = hashlib.sha256(SAMPLE_BYTES).hexdigest()

    assert client.post("/api/datasets/sample").status_code == 201

    assert SAMPLE.exists()
    assert hashlib.sha256(SAMPLE.read_bytes()).hexdigest() == before
    assert_no_leftovers(data_dir)
    assert not [p for p in data_dir.rglob("*") if ".staging-" in str(p)]


def test_two_calls_make_two_working_datasets(client, settings):
    first = client.post("/api/datasets/sample").json()
    second = client.post("/api/datasets/sample").json()

    assert first["dataset_id"] != second["dataset_id"]
    assert first["token"] != second["token"]
    for body in (first, second):
        assert verify_token(body["dataset_id"], body["token"], settings)
    assert len(list(settings.dataset_dir.glob("*.duckdb"))) == 2
    assert not verify_token(first["dataset_id"], second["token"], settings)


def test_body_and_form_fields_are_ignored(client):
    response = client.post("/api/datasets/sample", data={"currency": "EUR"})
    assert response.status_code == 201
    assert response.json()["meta"]["currency"] == "USD"

    response = client.post("/api/datasets/sample", json={"currency": "EUR"})
    assert response.status_code == 201
    assert response.json()["meta"]["currency"] == "USD"

    response = client.post(
        "/api/datasets/sample",
        files={"file": ("x.csv", "garbage", "text/csv")},
        data={"currency": "EUR"},
    )
    assert response.status_code == 201
    assert response.json()["meta"]["currency"] == "USD"


@pytest.mark.parametrize("demo", [True, False])
def test_demo_mode_does_not_matter(data_dir, demo):
    settings = Settings(DATASET_DIR=data_dir, PUBLIC_DEMO_MODE=demo)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        assert TestClient(app).post("/api/datasets/sample").status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_route_is_not_captured_by_a_dataset_id_route():
    # OpenAPI paths are listed in route order; a parameterised route under
    # /api/datasets/ must not come before the literal sample route.
    paths = [path for path, ops in app.openapi()["paths"].items() if "post" in ops]
    assert "/api/datasets/sample" in paths
    for path in paths[: paths.index("/api/datasets/sample")]:
        assert not path.startswith("/api/datasets/{")


# --- failures ---


def assert_unavailable(response, data_dir, hidden):
    assert response.status_code == 500
    body = response.json()
    assert list(body) == ["error"]
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "sample_unavailable"
    for text in [str(data_dir), str(SAMPLE), "Traceback", *hidden]:
        assert text not in response.text
    assert not list(data_dir.glob("*.duckdb*"))
    assert_clean(data_dir)


def test_broken_sample_is_500_sample_unavailable(client, data_dir, tmp_path, monkeypatch):
    broken = tmp_path / "broken.csv"
    broken.write_text("order_id,order_date,product_id,product_name,quantity,unit_price\no1,not-a-date,p1,Mug,1,2.00\n")
    monkeypatch.setattr(datasets_module, "SAMPLE_CSV", broken)

    assert_unavailable(client.post("/api/datasets/sample"), data_dir, [str(broken)])
    assert broken.exists()


def test_bad_structure_sample_is_500(client, data_dir, tmp_path, monkeypatch):
    broken = tmp_path / "empty.csv"
    broken.write_bytes(b"")
    monkeypatch.setattr(datasets_module, "SAMPLE_CSV", broken)

    assert_unavailable(client.post("/api/datasets/sample"), data_dir, [str(broken)])


def test_missing_sample_is_500(client, data_dir, tmp_path, monkeypatch):
    missing = tmp_path / "nope.csv"
    monkeypatch.setattr(datasets_module, "SAMPLE_CSV", missing)

    assert_unavailable(client.post("/api/datasets/sample"), data_dir, [str(missing)])


def test_failure_inside_the_import_is_500_and_leaves_nothing(client, data_dir, monkeypatch):
    import app.ingest as ingest_module

    def boom(*args, **kwargs):
        raise RuntimeError(f"secret {data_dir}")

    monkeypatch.setattr(ingest_module, "import_dataset", boom)

    assert_unavailable(client.post("/api/datasets/sample"), data_dir, ["secret"])


def test_sample_uses_the_shared_ingest_function(client, monkeypatch):
    calls = []
    real = datasets_module.ingest_csv

    def spy(path, currency, settings, *args):
        calls.append(currency)
        return real(path, currency, settings, *args)

    monkeypatch.setattr(datasets_module, "ingest_csv", spy)

    assert client.post("/api/datasets/sample").status_code == 201
    assert calls == ["USD"]
