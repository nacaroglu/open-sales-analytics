import subprocess
import sys
from pathlib import Path

from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]


def test_invalid_value_stops_the_server_with_nonzero_exit(monkeypatch):
    monkeypatch.setenv("MAX_ROWS", "0")
    get_settings.cache_clear()
    try:
        with TestClient(app):
            raise AssertionError("app started with an invalid MAX_ROWS")
    except Exception as exc:  # noqa: BLE001 - any startup failure is the point
        assert "MAX_ROWS" in str(exc)
    finally:
        get_settings.cache_clear()


def test_uvicorn_exits_nonzero_on_invalid_environment(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(BACKEND),
            "--port",
            "8769",
        ],
        env={"MAX_UPLOAD_BYTES": "-1", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "MAX_UPLOAD_BYTES" in result.stderr
