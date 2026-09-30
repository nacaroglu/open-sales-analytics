from pathlib import Path

import pytest
from app.errors import register_error_handlers
from app.main import app as real_app
from app.main import mount_frontend
from fastapi import FastAPI
from fastapi.testclient import TestClient

INDEX_HTML = "<!doctype html><title>fake spa</title><div id=root></div>"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML)
    (dist / "assets" / "app-abc123.js").write_text("console.log(1);")
    (dist / "assets" / "app-abc123.css").write_text("body{margin:0}")
    (tmp_path / "secret.txt").write_text("outside the build")

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/only-post")
    def only_post() -> dict[str, str]:
        return {"ok": "yes"}

    mount_frontend(app, dist)
    return TestClient(app)


def test_root_returns_index_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX_HTML


@pytest.mark.parametrize("path", ["/d/anything", "/d/a/b/c", "/some-page", "/favicon.ico"])
def test_deep_links_return_index_html(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["content-type"].startswith("text/html")


def test_head_on_a_deep_link_is_served(client):
    response = client.head("/d/anything")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/does-not-exist", "/api/datasets/x/y"])
def test_unknown_api_paths_return_the_json_404_not_index_html(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"


def test_existing_api_route_still_works(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_wrong_method_on_an_api_route_keeps_the_json_405(client):
    response = client.get("/api/only-post")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


@pytest.mark.parametrize("path", ["/api/does-not-exist", "/d/anything", "/"])
def test_post_to_an_unknown_path_answers_with_the_json_envelope(client, path):
    response = client.post(path)

    assert response.status_code in (404, 405)
    assert response.headers["content-type"] == "application/json"
    assert "code" in response.json()["error"]


def test_assets_are_served_with_their_content_types(client):
    js = client.get("/assets/app-abc123.js")
    css = client.get("/assets/app-abc123.css")

    assert js.status_code == 200
    assert js.headers["content-type"].startswith("text/javascript")
    assert js.text == "console.log(1);"
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")


def test_missing_asset_is_a_json_404_not_index_html(client):
    response = client.get("/assets/missing.js")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "path",
    [
        "/%2e%2e/%2e%2e/etc/passwd",
        "/%2e%2e/secret.txt",
        "/assets/../../pyproject.toml",
        "/assets/../secret.txt",
        "/assets/%2e%2e/secret.txt",
        "/assets/..%2fsecret.txt",
        "/assets/%2e%2e%2fsecret.txt",
        "/..%2f..%2fetc/passwd",
        "/assets//etc/passwd",
        "/%252e%252e/secret.txt",
    ],
)
def test_path_traversal_never_reaches_a_file_outside_the_build(client, path):
    response = client.get(path)

    assert "outside the build" not in response.text
    assert "root:" not in response.text
    assert "open-sales-analytics" not in response.text
    assert response.status_code == 404 or response.text == INDEX_HTML


def test_real_app_keeps_its_api_whether_or_not_a_build_exists():
    client = TestClient(real_app)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/nope").json()["error"]["code"] == "not_found"


def test_app_without_the_fallback_answers_root_with_json_404():
    app = FastAPI()
    register_error_handlers(app)

    response = TestClient(app).get("/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
