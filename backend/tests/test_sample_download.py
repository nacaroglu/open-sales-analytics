import json
import logging

import pytest
from fastapi.testclient import TestClient

import app.api.datasets as datasets_module
from app.config import Settings, get_settings
from app.main import app

SAMPLE = datasets_module.SAMPLE_CSV
SAMPLE_BYTES = SAMPLE.read_bytes()
PATH = "/api/sample.csv"
UNAVAILABLE_MESSAGE = "The sample dataset is not available right now."


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def client(data_dir):
    settings = Settings(DATASET_DIR=data_dir)
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def log(capsys, monkeypatch):
    monkeypatch.setattr(logging.getLogger("httpx"), "disabled", True)
    capsys.readouterr()

    def read():
        return [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]

    return read


def test_download_is_200_csv_attachment_with_the_file_size(client):
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "text/csv"
    assert response.headers["content-disposition"] == 'attachment; filename="sample_sales.csv"'
    assert response.headers["content-length"] == str(SAMPLE.stat().st_size)


def test_body_is_byte_identical_to_the_committed_file(client):
    assert client.get(PATH).content == SAMPLE_BYTES


def test_garbage_bearer_token_is_ignored(client):
    response = client.get(PATH, headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 200
    assert response.content == SAMPLE_BYTES


def test_works_in_demo_mode_with_the_same_bytes(data_dir):
    demo = Settings(PUBLIC_DEMO_MODE=True, DATASET_DIR=data_dir)
    app.dependency_overrides[get_settings] = lambda: demo
    try:
        response = TestClient(app).get(PATH)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.content == SAMPLE_BYTES


def test_downloaded_bytes_upload_with_no_errors_and_no_warnings(client):
    downloaded = client.get(PATH).content
    response = client.post(
        "/api/datasets",
        files={"file": ("sample_sales.csv", downloaded, "text/csv")},
        data={"currency": "USD"},
    )
    assert response.status_code == 201
    assert response.json()["warnings"] == []


def test_request_writes_one_request_line_and_no_content(client, log):
    client.get(PATH)
    (line,) = log()
    assert line["logger"] == "osa.request"
    assert (line["method"], line["path"], line["status"], line["dataset_id"]) == (
        "GET",
        PATH,
        200,
        None,
    )
    assert "duration_ms" in line
    assert "sample_sales" not in json.dumps(line)
    assert "order_id" not in json.dumps(line)


def test_does_not_create_or_touch_the_dataset_dir(client, data_dir):
    assert client.get(PATH).status_code == 200
    assert not data_dir.exists()


def test_missing_file_is_500_sample_unavailable(client, tmp_path, monkeypatch, log):
    monkeypatch.setattr(datasets_module, "SAMPLE_CSV", tmp_path / "gone.csv")
    response = client.get(PATH)
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "sample_unavailable", "message": UNAVAILABLE_MESSAGE}}
    assert "Traceback" not in response.text
    assert str(tmp_path) not in response.text
    (line,) = log()
    assert line["status"] == 500


def test_missing_file_gives_the_same_error_as_the_sample_dataset_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "SAMPLE_CSV", tmp_path / "gone.csv")
    assert client.get(PATH).json() == client.post("/api/datasets/sample").json()


def test_route_serves_whatever_sample_csv_points_at_when_the_request_arrives(client, tmp_path, monkeypatch):
    other = tmp_path / "other.csv"
    other.write_bytes(b"a,b\n1,2\n")
    monkeypatch.setattr(datasets_module, "SAMPLE_CSV", other)
    response = client.get(PATH)
    assert response.content == b"a,b\n1,2\n"
    assert response.headers["content-disposition"] == 'attachment; filename="sample_sales.csv"'


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_other_methods_answer_the_json_405_envelope(client, method):
    response = getattr(client, method)(PATH)
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_the_datasets_path_is_not_the_route(client):
    response = client.get("/api/datasets/sample.csv")
    assert response.status_code == 401
    assert response.content != SAMPLE_BYTES


def test_unknown_api_paths_are_still_the_json_404(client):
    response = client.get("/api/sample.csv/extra")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert client.get("/api/sample").json()["error"]["code"] == "not_found"


def test_no_second_copy_of_the_sample_is_in_the_frontend():
    frontend = SAMPLE.parents[3] / "frontend"
    copies = [p for p in frontend.rglob("sample_sales.csv") if "node_modules" not in p.parts]
    assert copies == []
