import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings

VARIABLES = [
    "DATASET_DIR",
    "DATASET_TTL_HOURS",
    "MAX_UPLOAD_BYTES",
    "MAX_ROWS",
    "CLEANUP_INTERVAL_MINUTES",
    "MAX_DATASETS",
    "PUBLIC_DEMO_MODE",
]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_with_empty_environment():
    settings = Settings()

    assert settings.dataset_dir == Path("./tmp_datasets")
    assert settings.dataset_ttl_hours == 24
    assert settings.max_upload_bytes == 52_428_800
    assert settings.max_rows == 500_000
    assert settings.max_datasets == 200
    assert settings.public_demo_mode is False


@pytest.mark.parametrize(
    ("variable", "raw", "field", "expected"),
    [
        ("DATASET_DIR", "/srv/data", "dataset_dir", Path("/srv/data")),
        ("DATASET_TTL_HOURS", "6", "dataset_ttl_hours", 6),
        ("MAX_UPLOAD_BYTES", "1000", "max_upload_bytes", 1000),
        ("MAX_ROWS", "42", "max_rows", 42),
        ("MAX_DATASETS", "3", "max_datasets", 3),
        ("PUBLIC_DEMO_MODE", "true", "public_demo_mode", True),
    ],
)
def test_each_variable_overrides_its_field(monkeypatch, variable, raw, field, expected):
    monkeypatch.setenv(variable, raw)

    assert getattr(Settings(), field) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        ("TRUE", True),
        ("False", False),
        ("Yes", True),
        ("NO", False),
    ],
)
def test_public_demo_mode_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", raw)

    assert Settings().public_demo_mode is expected


def test_invalid_public_demo_mode_names_the_variable(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "maybe")

    with pytest.raises(ValidationError, match="PUBLIC_DEMO_MODE"):
        Settings()


@pytest.mark.parametrize(
    "variable", ["DATASET_TTL_HOURS", "MAX_UPLOAD_BYTES", "MAX_ROWS", "MAX_DATASETS"]
)
@pytest.mark.parametrize("raw", ["0", "-1", "-5", "abc", "1.5"])
def test_invalid_integers_name_the_variable(monkeypatch, variable, raw):
    monkeypatch.setenv(variable, raw)

    with pytest.raises(ValidationError, match=variable):
        Settings()


@pytest.mark.parametrize("variable", VARIABLES)
def test_empty_string_is_invalid_not_default(monkeypatch, variable):
    monkeypatch.setenv(variable, "")

    with pytest.raises(ValidationError, match=variable):
        Settings()


def test_get_settings_returns_the_same_object():
    assert get_settings() is get_settings()


def test_cache_can_be_cleared_between_tests(monkeypatch):
    first = get_settings()
    monkeypatch.setenv("MAX_ROWS", "7")

    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings().max_rows == 7


def test_building_settings_does_not_touch_the_filesystem(monkeypatch, tmp_path):
    target = tmp_path / "not-created"
    monkeypatch.setenv("DATASET_DIR", str(target))

    Settings()

    assert not target.exists()


def test_only_config_reads_the_environment():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        path.name
        for path in app_dir.rglob("*.py")
        if path.name != "config.py" and re.search(r"os\.environ|os\.getenv", path.read_text())
    ]

    assert offenders == []
