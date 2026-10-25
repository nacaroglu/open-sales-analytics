import pytest
from app import health
from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture
def initialized_client(monkeypatch, tmp_path):
    data_dir = tmp_path / "datasets"
    monkeypatch.setenv("DATASET_DIR", str(data_dir))
    monkeypatch.setenv("OSA_ENVIRONMENT", "production")
    monkeypatch.setenv("OSA_VERSION", "20261025-120000-abc1234")
    get_settings.cache_clear()
    try:
        with TestClient(app) as test_client:
            yield test_client, data_dir
    finally:
        get_settings.cache_clear()


def test_health_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_health_needs_no_authorization_header():
    response = client.get("/api/health", headers={})

    assert response.status_code == 200


def test_health_works_without_dataset_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "does-not-exist"))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert not (tmp_path / "does-not-exist").exists()


def test_health_rejects_post():
    response = client.post("/api/health")

    assert response.status_code == 405


def test_unknown_api_path_returns_json_404():
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert isinstance(response.json(), dict)


def test_cross_origin_request_gets_no_cors_headers():
    response = client.get("/api/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_liveness_is_process_only_even_when_readiness_is_not_available(monkeypatch):
    monkeypatch.setattr(app.state, "initialized", False)
    monkeypatch.setattr(
        health,
        "readiness_checks",
        lambda _: pytest.fail("liveness must not run readiness checks"),
    )

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_readiness_is_503_before_initialization_and_does_not_probe(monkeypatch):
    monkeypatch.setattr(app.state, "initialized", False)
    monkeypatch.setattr(
        health,
        "readiness_checks",
        lambda _: pytest.fail("readiness dependencies must wait for initialization"),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_returns_exact_safe_identity_and_cleans_probes(initialized_client):
    test_client, data_dir = initialized_client

    response = test_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "open-sales-analytics",
        "environment": "production",
        "version": "20261025-120000-abc1234",
    }
    assert response.headers["cache-control"] == "no-store"
    assert [path.name for path in data_dir.iterdir()] == ["uploads"]
    assert list((data_dir / "uploads").iterdir()) == []


@pytest.mark.parametrize(
    "failed_check",
    ["storage_is_writable", "duckdb_is_usable", "sample_assets_are_available"],
)
def test_readiness_returns_generic_503_when_a_dependency_fails(
    initialized_client, monkeypatch, tmp_path, failed_check
):
    test_client, _ = initialized_client
    monkeypatch.setattr(health, failed_check, lambda *_: False)

    response = test_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert str(tmp_path) not in response.text
    assert "secret" not in response.text
    assert "traceback" not in response.text.lower()


def test_readiness_sanitizes_probe_exceptions(initialized_client, monkeypatch, tmp_path):
    test_client, _ = initialized_client
    secret_error = f"private path {tmp_path}/secret"

    def fail_with_sensitive_details(_):
        raise OSError(secret_error)

    monkeypatch.setattr(health, "readiness_checks", fail_with_sensitive_details)

    response = test_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert secret_error not in response.text


def test_storage_probe_removes_file_when_write_fails(monkeypatch, tmp_path):
    directory = tmp_path / "datasets"
    directory.mkdir()

    def fail_after_create(descriptor, *_args, **_kwargs):
        import os

        os.close(descriptor)
        raise OSError("probe failed")

    monkeypatch.setattr(health.os, "fdopen", fail_after_create)

    assert not health.storage_is_writable(directory)
    assert list(directory.iterdir()) == []


def test_duckdb_probe_removes_file_when_connection_fails(monkeypatch, tmp_path):
    directory = tmp_path / "datasets"
    directory.mkdir()
    monkeypatch.setattr(
        health.duckdb,
        "connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("database failed")),
    )

    assert not health.duckdb_is_usable(directory)
    assert list(directory.iterdir()) == []


def test_sample_asset_check_fails_when_file_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "SAMPLE_CSV", tmp_path / "missing.csv")

    assert not health.sample_assets_are_available()
