from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


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
