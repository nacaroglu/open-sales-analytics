import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

import app.ingest as ingest_module
from app.config import Settings, get_settings
from app.logging_config import JsonFormatter, configure_logging
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
ID = "A" * 22


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data")


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def log(capsys, monkeypatch):
    """Everything written to the log so far, as raw text; the JSON lines are ``.lines``."""

    class Log:
        def __init__(self):
            self.text = ""

        def read(self):
            self.text += capsys.readouterr().err
            return self.text

        def clear(self):
            self.read()
            self.text = ""

        @property
        def lines(self):
            return [json.loads(line) for line in self.read().splitlines() if line.strip()]

        def requests(self):
            return [line for line in self.lines if line["logger"] == "osa.request"]

    # The test client's own request logging is not part of the app.
    monkeypatch.setattr(logging.getLogger("httpx"), "disabled", True)
    capsys.readouterr()
    return Log()


def upload(client, csv, currency="USD", name="x.csv"):
    return client.post(
        "/api/datasets",
        files={"file": (name, csv.encode(), "text/csv")},
        data={"currency": currency},
    )


def good_csv():
    return HEADER + "\no1,2025-01-02,p1,Mug,2,19.99\n"


# --- format ---


def test_every_line_is_one_json_object_with_the_required_keys(client, log):
    client.get("/api/health")
    client.get("/api/nothing")
    for line in log.lines:
        assert {"timestamp", "level", "logger", "message"} <= line.keys()
        assert line["timestamp"].endswith(("Z", "+00:00"))


def test_encoded_newline_in_the_path_stays_on_one_line(client, log):
    client.get("/api/x%0Afake%0D%1B[31m")
    text = log.read()
    assert len(text.splitlines()) == 1
    entry = json.loads(text)
    assert entry["path"] == "/api/x\nfake\r\x1b[31m"


def test_formatter_escapes_control_characters_in_messages():
    record = logging.LogRecord("t", logging.INFO, "f", 1, "a\nb\x00c d", None, None)
    out = JsonFormatter().format(record)
    assert "\n" not in out and "\x00" not in out and " " not in out
    assert json.loads(out)["message"] == "a\nb\x00c d"


def test_root_level_is_info_and_debug_output_is_dropped(log):
    assert logging.getLogger().level == logging.INFO
    logging.getLogger("python_multipart.multipart").debug("chunk data MARKER_CHUNK")
    assert "MARKER_CHUNK" not in log.read()


def test_setup_is_idempotent(client, log):
    import importlib

    import app.main

    before = len(logging.getLogger().handlers)
    importlib.reload(app.main)
    configure_logging()
    assert len(logging.getLogger().handlers) == before
    TestClient(app.main.app).get("/api/health")
    TestClient(app.main.app).get("/api/health")
    assert len(log.requests()) == 2


def test_other_loggers_use_the_same_format(log):
    logging.getLogger("app.cleanup").info("cleanup sweep: 0 datasets removed")
    (line,) = log.lines
    assert line["logger"] == "app.cleanup"
    assert line["message"] == "cleanup sweep: 0 datasets removed"


def test_demo_rejection_line_is_json(tmp_path, log):
    demo = Settings(PUBLIC_DEMO_MODE=True, DATASET_DIR=tmp_path / "d")
    app.dependency_overrides[get_settings] = lambda: demo
    try:
        assert upload(TestClient(app), good_csv()).status_code == 403
    finally:
        app.dependency_overrides.clear()
    names = [line["logger"] for line in log.lines]
    assert names == ["app.api.datasets", "osa.request"]


# --- request line ---


def test_each_outcome_writes_exactly_one_request_line(client, log):
    client.get("/api/health")
    client.get("/api/unknown")
    client.options("/api/health")
    client.get("/api/datasets/" + ID)
    client.get("/api/datasets/" + ID, params={"x": "1"})
    lines = log.requests()
    assert [(r["method"], r["status"]) for r in lines] == [
        ("GET", 200),
        ("GET", 404),
        ("OPTIONS", 405),
        ("GET", 401),
        ("GET", 401),
    ]
    assert all(isinstance(r["duration_ms"], (int, float)) for r in lines)
    assert all(r["level"] == "INFO" for r in lines)


def test_path_has_no_query_string(client, log):
    created = upload(client, good_csv()).json()
    log.clear()
    client.get(
        f"/api/datasets/{created['dataset_id']}/analytics?start=2025-01-01",
        headers={"Authorization": f"Bearer {created['token']}"},
    )
    (line,) = log.requests()
    assert line["path"] == f"/api/datasets/{created['dataset_id']}/analytics"
    assert "start" not in json.dumps(line)
    assert line["dataset_id"] == created["dataset_id"]


def test_dataset_id_is_null_unless_the_path_holds_a_well_formed_id(client, log):
    client.get("/api/datasets/sample")
    client.get("/api/datasets/junk")
    client.get("/api/health")
    assert [r["dataset_id"] for r in log.requests()] == [None, None, None]


def test_created_dataset_id_is_logged_for_upload_and_sample(client, log):
    uploaded = upload(client, good_csv())
    sample = client.post("/api/datasets/sample")
    lines = log.requests()
    assert [r["status"] for r in lines] == [201, 201]
    assert lines[0]["dataset_id"] == uploaded.json()["dataset_id"]
    assert lines[1]["dataset_id"] == sample.json()["dataset_id"]


def test_dataset_id_is_null_for_a_failed_upload(client, log):
    assert upload(client, good_csv(), currency="XXX").status_code == 400
    assert upload(client, HEADER + "\no1,2025-01-02,p1,Mug,abc,19.99\n").status_code == 422
    assert [r["dataset_id"] for r in log.requests()] == [None, None]


# --- unhandled exceptions ---


def force_import_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("Conversion error near MARKER_ROW_VALUE")

    monkeypatch.setattr(ingest_module, "import_dataset", boom)


def test_swallowed_failure_is_logged_with_class_and_frames_only(client, log, monkeypatch):
    force_import_failure(monkeypatch)
    response = upload(client, good_csv())
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong on the server."}
    }
    lines = log.lines
    assert "MARKER_ROW_VALUE" not in log.text
    errors = [line for line in lines if line["logger"] == "app.api.datasets"]
    assert len(errors) == 1
    assert errors[0]["level"] == "ERROR"
    assert errors[0]["exception"] == "RuntimeError"
    assert {"file", "line", "function"} == set(errors[0]["frames"][0])
    assert any(f["function"] == "boom" for f in errors[0]["frames"])
    (request_line,) = log.requests()
    assert request_line["status"] == 500 and request_line["level"] == "ERROR"
    assert request_line["dataset_id"] is None


def test_sample_failures_are_logged_too(client, log, monkeypatch):
    force_import_failure(monkeypatch)
    assert client.post("/api/datasets/sample").status_code == 500
    assert "MARKER_ROW_VALUE" not in log.read()
    assert [line["exception"] for line in log.lines if "exception" in line] == ["RuntimeError"]


def test_unhandled_exception_writes_request_line_and_one_error_line(client, log):
    @app.get("/api/_boom")
    def boom():
        try:
            raise KeyError("MARKER_INNER")
        except KeyError as inner:
            raise ValueError("MARKER_OUTER row 7") from inner

    try:
        response = client.get("/api/_boom")
    finally:
        app.router.routes.pop()
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong on the server."}
    }
    text = log.read()
    assert "MARKER" not in text and "Traceback" not in text
    lines = log.lines
    assert len(lines) == 2
    error = next(line for line in lines if line["logger"] == "osa.error")
    assert error["level"] == "ERROR"
    assert error["exception"] == "ValueError"
    assert error["chained"] == ["KeyError"]
    assert any(f["function"] == "boom" for f in error["frames"])
    (request_line,) = log.requests()
    assert request_line["status"] == 500 and request_line["level"] == "ERROR"


def test_logged_exception_info_never_includes_the_message(log):
    try:
        raise ValueError("MARKER_MSG")
    except ValueError:
        logging.getLogger("something.else").exception("failed")
    text = log.read()
    assert "MARKER_MSG" not in text
    assert json.loads(text)["exception"] == "ValueError"


# --- redaction ---


def test_successful_upload_leaves_no_marker_or_token_in_the_log(client, log):
    csv = (
        HEADER + ",MARKER_COLUMN\n"
        "MARKER_ORDER,2025-01-02,p1,MARKER_PRODUCT,2,19.99,MARKER_CELL\n"
    )
    response = upload(client, csv, name="MARKER_FILENAME.csv")
    assert response.status_code == 201
    text = log.read()
    assert text
    for marker in ("MARKER", response.json()["token"]):
        assert marker not in text


def test_failed_upload_leaves_the_invalid_value_out_of_the_log(client, log):
    csv = HEADER + "\no1,2025-01-02,p1,Mug,MARKER_BADQTY,19.99\n"
    response = upload(client, csv, name="MARKER_FILENAME.csv")
    assert response.status_code == 422
    assert "MARKER_BADQTY" in response.text
    text = log.read()
    assert text
    assert "MARKER" not in text


def test_authorization_headers_never_reach_the_log(client, log, settings):
    created = upload(client, good_csv()).json()
    log.clear()
    good = "Bearer " + created["token"]
    wrong = "Bearer MARKER_WRONG_TOKEN"
    assert client.get(f"/api/datasets/{created['dataset_id']}", headers={"Authorization": good}).status_code == 200
    assert client.get(f"/api/datasets/{created['dataset_id']}", headers={"Authorization": wrong}).status_code == 401
    text = log.read()
    assert created["token"] not in text
    assert "MARKER_WRONG_TOKEN" not in text
    assert "Bearer" not in text


def test_token_hash_never_reaches_the_log(client, log, settings):
    created = upload(client, good_csv()).json()
    client.get(
        f"/api/datasets/{created['dataset_id']}",
        headers={"Authorization": "Bearer " + created["token"]},
    )
    path = settings.dataset_dir / f"{created['dataset_id']}.duckdb"
    connection = duckdb.connect(str(path), read_only=True)
    try:
        token_hash = connection.execute("SELECT token_hash FROM dataset_meta").fetchone()[0]
    finally:
        connection.close()
    assert len(token_hash) == 64
    text = log.read()
    assert text and token_hash not in text


# --- a real uvicorn process ---


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_real_uvicorn_writes_one_json_request_line_per_request_and_no_access_log(tmp_path):
    port = free_port()
    output = tmp_path / "out.txt"
    env = {"PATH": os.environ.get("PATH", ""), "DATASET_DIR": str(tmp_path / "data")}
    with output.open("w") as sink:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND),
             "--port", str(port)],
            env=env, stdout=sink, stderr=subprocess.STDOUT,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + "/api/health", timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("server did not start")
            urllib.request.urlopen(url + "/api/health", timeout=5).read()
        finally:
            server.terminate()
            server.wait(timeout=15)

    lines = output.read_text().splitlines()
    request_lines = [line for line in lines if line.startswith("{") and '"osa.request"' in line]
    assert len(request_lines) == 2
    assert all(json.loads(line)["path"] == "/api/health" for line in request_lines)
    assert not any("HTTP/1.1" in line for line in lines)
