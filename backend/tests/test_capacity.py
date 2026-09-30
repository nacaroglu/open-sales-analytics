import json
import logging
import threading
from datetime import UTC, datetime, timedelta

import app.api.datasets as datasets
import app.capacity as capacity
import duckdb
import pytest
from app.auth import get_now
from app.capacity import count_live_datasets
from app.cleanup import sweep
from app.config import Settings, get_settings
from app.main import app
from app.schema import create_dataset
from app.tokens import new_dataset_id
from fastapi.testclient import TestClient

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
GOOD = HEADER + "\no1,2025-01-02,p1,Mug,2,19.99\n"
BODY = {
    "error": {
        "code": "capacity_reached",
        "message": "The server is holding the maximum number of datasets right now. Try again later.",
    }
}


def make_settings(tmp_path, cap, **extra):
    return Settings(DATASET_DIR=tmp_path / "data", MAX_DATASETS=cap, **extra)


def make_dataset(settings, expires_at, with_meta=True):
    settings.dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = new_dataset_id()
    path = settings.dataset_dir / f"{dataset_id}.duckdb"
    create_dataset(path)
    if with_meta:
        connection = duckdb.connect(str(path))
        connection.execute(
            "INSERT INTO dataset_meta VALUES (?, 'EUR', ?, ?, 'hash', 1)",
            [dataset_id, NOW - timedelta(hours=1), expires_at],
        )
        connection.close()
    return path


def live(settings, n=1):
    return [make_dataset(settings, NOW + timedelta(hours=1)) for _ in range(n)]


def expired(settings, n=1):
    return [make_dataset(settings, NOW - timedelta(seconds=1)) for _ in range(n)]


def snapshot(directory):
    return sorted((str(p.relative_to(directory)), p.stat().st_size) for p in directory.rglob("*"))


@pytest.fixture
def make_client():
    def build(settings, now=NOW):
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_now] = lambda: now
        return TestClient(app, raise_server_exceptions=False)

    yield build
    app.dependency_overrides.clear()


def post_sample(client):
    return client.post("/api/datasets/sample")


def post_upload(client, content=GOOD, currency="USD"):
    return client.post(
        "/api/datasets",
        data={"currency": currency},
        files={"file": ("x.csv", content, "text/csv")},
    )


CREATORS = [pytest.param(post_sample, id="sample"), pytest.param(post_upload, id="upload")]


# --- the counting function ---


def test_missing_directory_counts_zero_and_is_not_created(tmp_path):
    settings = make_settings(tmp_path, 5)

    assert count_live_datasets(settings, NOW, 5) == 0
    assert not settings.dataset_dir.exists()


def test_counts_only_unexpired_datasets(tmp_path):
    settings = make_settings(tmp_path, 10)
    live(settings, 3)
    expired(settings, 2)

    assert count_live_datasets(settings, NOW, 10) == 3


def test_expiry_exactly_now_is_not_live_one_second_later_is(tmp_path):
    settings = make_settings(tmp_path, 10)
    make_dataset(settings, NOW)
    assert count_live_datasets(settings, NOW, 10) == 0
    make_dataset(settings, NOW + timedelta(seconds=1))
    assert count_live_datasets(settings, NOW, 10) == 1


def test_broken_and_metadata_less_files_do_not_count(tmp_path):
    settings = make_settings(tmp_path, 10)
    make_dataset(settings, NOW + timedelta(hours=1), with_meta=False)
    (settings.dataset_dir / f"{new_dataset_id()}.duckdb").write_bytes(b"not a database")
    (settings.dataset_dir / f"{new_dataset_id()}.duckdb").write_bytes(b"")
    live(settings)

    assert count_live_datasets(settings, NOW, 10) == 1


def test_other_names_symlinks_and_directories_are_ignored(tmp_path):
    settings = make_settings(tmp_path, 10)
    (real,) = live(settings)
    directory = settings.dataset_dir
    content = real.read_bytes()
    (directory / "uploads").mkdir()
    (directory / f"{new_dataset_id()}.duckdb.wal").write_bytes(b"x")
    (directory / f".{new_dataset_id()}.duckdb.importing").write_bytes(content)
    (directory / "short.duckdb").write_bytes(content)
    (directory / f"{new_dataset_id()}.duckdb.bak").write_bytes(content)
    (directory / f"{new_dataset_id()}.duckdb").mkdir()
    (directory / f"{new_dataset_id()}.duckdb").symlink_to(real)

    assert count_live_datasets(settings, NOW, 10) == 1


def test_counting_stops_at_the_limit_without_opening_the_rest(tmp_path, monkeypatch):
    settings = make_settings(tmp_path, 2)
    live(settings, 5)
    opened = []
    original = capacity._is_expired_or_broken

    def spy(path, now):
        opened.append(path)
        return original(path, now)

    monkeypatch.setattr(capacity, "_is_expired_or_broken", spy)

    assert count_live_datasets(settings, NOW, 2) == 2
    assert len(opened) == 2


def test_counting_has_no_second_expiry_comparison_and_no_pytz():
    source = open(capacity.__file__).read()

    assert "pytz" not in source
    assert "expires_at" not in source  # the SQL lives in app.auth, reused via cleanup


# --- rejection ---


@pytest.mark.parametrize("create", CREATORS)
def test_at_capacity_answers_503_and_creates_nothing(tmp_path, make_client, create):
    settings = make_settings(tmp_path, 2)
    live(settings, 2)
    (settings.dataset_dir / "uploads").mkdir()
    before = snapshot(settings.dataset_dir)

    response = create(make_client(settings))

    assert response.status_code == 503
    assert response.json() == BODY
    assert "retry-after" not in response.headers
    assert snapshot(settings.dataset_dir) == before


@pytest.mark.parametrize("create", CREATORS)
def test_over_capacity_also_answers_503(tmp_path, make_client, create):
    settings = make_settings(tmp_path, 2)
    live(settings, 3)

    assert create(make_client(settings)).status_code == 503


def test_at_capacity_an_invalid_upload_is_503_and_no_temp_file_appears(tmp_path, make_client):
    settings = make_settings(tmp_path, 1)
    live(settings)
    (settings.dataset_dir / "uploads").mkdir()
    before = snapshot(settings.dataset_dir)
    client = make_client(settings)

    for response in (
        post_upload(client, "not,a,valid\nfile\n"),
        post_upload(client, GOOD, currency="XXX"),
        client.post("/api/datasets", content=b"garbage", headers={"Content-Type": "text/plain"}),
        client.post("/api/datasets"),
    ):
        assert response.status_code == 503
        assert response.json() == BODY
    assert snapshot(settings.dataset_dir) == before


def test_at_capacity_an_oversized_upload_is_503_not_413(tmp_path, make_client):
    settings = make_settings(tmp_path, 1, MAX_UPLOAD_BYTES=100)
    live(settings)
    (settings.dataset_dir / "uploads").mkdir()
    before = snapshot(settings.dataset_dir)

    response = post_upload(make_client(settings), GOOD + "x" * 10_000)

    assert response.status_code == 503
    assert snapshot(settings.dataset_dir) == before


def test_the_body_is_not_read_when_at_capacity(tmp_path, make_client, monkeypatch):
    settings = make_settings(tmp_path, 1)
    live(settings)

    async def boom(*args, **kwargs):
        raise AssertionError("body was read")

    monkeypatch.setattr(datasets, "_receive", boom)

    assert post_upload(make_client(settings)).status_code == 503


def test_demo_mode_403_wins_over_the_cap(tmp_path, make_client):
    settings = make_settings(tmp_path, 1, PUBLIC_DEMO_MODE=True)
    live(settings)

    response = post_upload(make_client(settings))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "upload_disabled"


def test_demo_mode_sample_is_still_capped(tmp_path, make_client):
    settings = make_settings(tmp_path, 1, PUBLIC_DEMO_MODE=True)
    live(settings)

    assert post_sample(make_client(settings)).status_code == 503


# --- boundaries ---


@pytest.mark.parametrize("create", CREATORS)
def test_one_below_the_cap_creates_then_the_next_is_refused(tmp_path, make_client, create):
    settings = make_settings(tmp_path, 3)
    live(settings, 2)
    client = make_client(settings)

    assert create(client).status_code == 201
    assert create(client).status_code == 503
    assert create(client).status_code == 503


def test_cap_of_one_on_an_empty_directory(tmp_path, make_client):
    client = make_client(make_settings(tmp_path, 1))

    assert post_sample(client).status_code == 201
    assert post_upload(client).status_code == 503


@pytest.mark.parametrize("create", CREATORS)
def test_expired_unswept_datasets_do_not_block(tmp_path, make_client, create):
    settings = make_settings(tmp_path, 2)
    expired(settings, 2)
    live(settings)

    assert create(make_client(settings)).status_code == 201


def test_broken_files_do_not_block(tmp_path, make_client):
    settings = make_settings(tmp_path, 1)
    make_dataset(settings, NOW + timedelta(hours=1), with_meta=False)
    (settings.dataset_dir / f"{new_dataset_id()}.duckdb").write_bytes(b"junk")

    assert post_sample(make_client(settings)).status_code == 201


def test_time_passing_frees_the_slot(tmp_path, make_client):
    settings = make_settings(tmp_path, 1)
    live(settings)

    assert post_sample(make_client(settings, NOW)).status_code == 503
    assert post_sample(make_client(settings, NOW + timedelta(hours=2))).status_code == 201


# --- freeing capacity ---


@pytest.mark.parametrize("create", CREATORS)
def test_delete_frees_a_slot_for_the_next_create(tmp_path, make_client, create):
    client = make_client(make_settings(tmp_path, 2))
    first = post_sample(client).json()
    assert post_sample(client).status_code == 201
    assert create(client).status_code == 503

    deleted = client.delete(
        f"/api/datasets/{first['dataset_id']}",
        headers={"Authorization": f"Bearer {first['token']}"},
    )

    assert deleted.status_code == 204
    assert create(client).status_code == 201
    assert create(client).status_code == 503


def test_sweep_frees_a_slot_for_the_next_create(tmp_path, make_client):
    settings = make_settings(tmp_path, 1)
    (path,) = expired(settings)
    live(settings)
    later = NOW + timedelta(hours=2)
    assert post_sample(make_client(settings)).status_code == 503

    sweep(settings, later)

    assert path.exists() is False
    assert post_sample(make_client(settings, later)).status_code == 201


def test_other_endpoints_are_not_affected_by_the_cap(tmp_path, make_client):
    client = make_client(make_settings(tmp_path, 1))
    created = post_sample(client).json()
    headers = {"Authorization": f"Bearer {created['token']}"}
    base = f"/api/datasets/{created['dataset_id']}"

    assert post_sample(client).status_code == 503
    assert client.get(base, headers=headers).status_code == 200
    assert client.get(base + "/analytics", headers=headers).status_code == 200
    assert client.get("/api/sample.csv").status_code == 200
    assert client.delete(base, headers=headers).status_code == 204


# --- logging and threading ---


def test_rejection_logs_one_info_record_and_one_503_request_line(
    tmp_path, make_client, capsys, monkeypatch
):
    settings = make_settings(tmp_path, 1)
    (path,) = live(settings)
    client = make_client(settings)
    monkeypatch.setattr(logging.getLogger("httpx"), "disabled", True)
    capsys.readouterr()

    response = post_sample(client)

    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert response.status_code == 503
    assert [(line["logger"], line["level"]) for line in lines] == [
        ("app.api.datasets", "INFO"),
        ("osa.request", "ERROR"),
    ]
    assert lines[0]["message"] == "Dataset creation refused because the server is at capacity."
    assert lines[1]["status"] == 503
    assert lines[1]["dataset_id"] is None
    text = json.dumps(lines)
    assert path.stem not in text
    assert str(tmp_path) not in text
    assert ".duckdb" not in text


def test_no_app_record_is_logged_when_there_is_room(tmp_path, make_client, caplog):
    client = make_client(make_settings(tmp_path, 2))

    with caplog.at_level(logging.INFO, logger="app"):
        assert post_sample(client).status_code == 201

    assert [r for r in caplog.records if r.name.startswith("app")] == []


def test_the_count_runs_in_a_worker_thread(tmp_path, make_client, monkeypatch):
    threads = []
    original = datasets.count_live_datasets

    def spy(*args, **kwargs):
        threads.append(threading.current_thread())
        return original(*args, **kwargs)

    monkeypatch.setattr(datasets, "count_live_datasets", spy)

    assert post_sample(make_client(make_settings(tmp_path, 2))).status_code == 201
    assert threads
    assert all(t is not threading.main_thread() for t in threads)
