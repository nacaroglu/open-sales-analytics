"""Static checks of the one-container packaging (Dockerfile, .dockerignore, README).

The packaged image itself is verified by the CI job ``docker-smoke`` and by the commands in the
comment on issue #48; these tests keep the files that define it from drifting.
"""

import re
from pathlib import Path

import pytest
from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
README = (ROOT / "README.md").read_text()


def _ignored() -> set[str]:
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _runtime_stage() -> str:
    return DOCKERFILE.split("\nFROM ")[-1]


def test_dockerfile_builds_the_frontend_in_a_stage_the_runtime_image_does_not_use():
    stages = DOCKERFILE.count("\nFROM ") + 1
    runtime = _runtime_stage()

    assert stages >= 3
    assert "FROM node" in DOCKERFILE
    assert "node" not in runtime.splitlines()[0]
    assert "npm" not in runtime.replace("COPY --from=frontend", "")
    assert "COPY --from=frontend /build/frontend/dist" in runtime


def test_runtime_image_runs_as_a_non_root_user_with_a_private_data_directory():
    runtime = _runtime_stage()

    assert re.search(r"^USER 10001$", runtime, re.MULTILINE)
    assert "chown app:app /data" in runtime
    assert "chmod 700 /data" in runtime
    assert "DATASET_DIR=/data" in runtime


def test_runtime_image_declares_a_healthcheck_on_the_health_endpoint_and_runs_uvicorn_directly():
    runtime = _runtime_stage()

    assert "HEALTHCHECK" in runtime
    assert "/api/health" in runtime
    assert re.search(r'^CMD \["uvicorn", "app.main:app"', runtime, re.MULTILINE)


def test_dockerignore_keeps_dev_output_local_data_and_secrets_out_of_the_build_context():
    ignored = _ignored()
    required = {
        ".git",
        ".venv",
        "**/node_modules",
        "frontend/dist",
        "frontend/test-results",
        "tmp_datasets",
        "*.duckdb",
        ".env",
        ".env.*",
        "**/.env",
        "**/*.pem",
        "**/*.key",
        "**/*credentials*",
        "**/*secret*",
    }

    assert required <= ignored, sorted(required - ignored)


def test_readme_documents_the_defaults_the_settings_have(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "DATASET_TTL_HOURS",
        "MAX_UPLOAD_BYTES",
        "MAX_ROWS",
        "CLEANUP_INTERVAL_MINUTES",
        "MAX_DATASETS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    row = {
        "DATASET_TTL_HOURS": str(settings.dataset_ttl_hours),
        "MAX_UPLOAD_BYTES": str(settings.max_upload_bytes),
        "MAX_ROWS": str(settings.max_rows),
        "CLEANUP_INTERVAL_MINUTES": str(settings.cleanup_interval_minutes),
        "MAX_DATASETS": str(settings.max_datasets),
    }

    for name, default in row.items():
        line = next(x for x in README.splitlines() if x.startswith(f"| `{name}`"))
        assert f"`{default}`" in line, name
    assert settings.max_upload_bytes == 50 * 1024 * 1024
    assert settings.max_rows == 500_000
