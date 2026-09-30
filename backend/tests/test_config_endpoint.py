import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.main import app, mount_frontend

PATH = "/api/config"
DEFAULTS = {"public_demo_mode": False, "max_upload_bytes": 52428800, "max_rows": 500000}


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


def client_for(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(data_dir):
    yield client_for(Settings(DATASET_DIR=data_dir))
    app.dependency_overrides.clear()


@pytest.fixture
def log(capsys, monkeypatch):
    monkeypatch.setattr(logging.getLogger("httpx"), "disabled", True)
    capsys.readouterr()

    def read():
        return [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]

    return read


def test_defaults_are_exactly_three_keys(client):
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == DEFAULTS
    assert list(response.json()) == ["public_demo_mode", "max_upload_bytes", "max_rows"]


def test_values_come_from_the_settings(data_dir):
    settings = Settings(
        PUBLIC_DEMO_MODE=True, MAX_UPLOAD_BYTES=1000, MAX_ROWS=7, DATASET_DIR=data_dir
    )
    try:
        body = client_for(settings).get(PATH).json()
    finally:
        app.dependency_overrides.clear()
    assert body == {"public_demo_mode": True, "max_upload_bytes": 1000, "max_rows": 7}


def test_values_are_read_from_the_environment_through_get_settings(monkeypatch, data_dir):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1000")
    monkeypatch.setenv("MAX_ROWS", "7")
    monkeypatch.setenv("DATASET_DIR", str(data_dir))
    get_settings.cache_clear()
    try:
        body = TestClient(app).get(PATH).json()
    finally:
        get_settings.cache_clear()
    assert body == {"public_demo_mode": True, "max_upload_bytes": 1000, "max_rows": 7}


def test_response_is_not_cacheable(client):
    assert client.get(PATH).headers["cache-control"] == "no-store"


@pytest.mark.parametrize("header", [None, "Bearer nonsense", "Basic abc", "Bearer"])
def test_no_authorization_is_needed_and_any_header_is_ignored(client, header):
    headers = {} if header is None else {"Authorization": header}
    response = client.get(PATH, headers=headers)
    assert response.status_code == 200
    assert response.json() == DEFAULTS


def test_unknown_query_parameters_are_ignored(client):
    response = client.get(PATH, params={"public_demo_mode": "true", "x": "1"})
    assert response.status_code == 200
    assert response.json() == DEFAULTS


def test_exposes_nothing_beyond_the_three_values(data_dir):
    settings = Settings(DATASET_DIR=data_dir / "secret-place")
    try:
        text = client_for(settings).get(PATH).text
    finally:
        app.dependency_overrides.clear()
    assert "secret-place" not in text
    for word in ("dir", "ttl", "interval", "token"):
        assert word not in text.lower()


def test_works_when_the_dataset_dir_is_missing_and_creates_nothing(client, data_dir):
    assert not data_dir.exists()
    assert client.get(PATH).status_code == 200
    assert not data_dir.exists()


def test_demo_mode_does_not_block_it_and_reports_true(data_dir):
    try:
        response = client_for(Settings(PUBLIC_DEMO_MODE=True, DATASET_DIR=data_dir)).get(PATH)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["public_demo_mode"] is True


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_other_methods_answer_the_json_405_envelope(client, method):
    response = getattr(client, method)(PATH)
    assert response.status_code == 405
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_request_writes_one_request_line_and_nothing_else(client, log):
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
    assert "52428800" not in json.dumps(line)


def test_other_unknown_api_paths_are_still_the_json_404(client):
    for path in ("/api/config/extra", "/api/configs"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_the_single_page_app_fallback_does_not_shadow_it(tmp_path, data_dir):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>")
    fresh = FastAPI()
    register_error_handlers(fresh)
    fresh.router.routes.extend(r for r in app.routes if getattr(r, "path", None) == PATH)
    mount_frontend(fresh, dist)
    fresh.dependency_overrides[get_settings] = lambda: Settings(DATASET_DIR=data_dir)

    http = TestClient(fresh)
    response = http.get(PATH)
    assert response.status_code == 200
    assert response.json() == DEFAULTS
    assert http.get("/api/config/extra").json()["error"]["code"] == "not_found"
