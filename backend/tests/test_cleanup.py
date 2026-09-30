import asyncio
import logging
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.cleanup as cleanup
from app.cleanup import prepare_dataset_dir, run_cleanup_loop, run_sweep_safely, sweep
from app.config import Settings, get_settings
from app.main import app
from app.schema import create_dataset
from app.tokens import new_dataset_id

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HOUR = 3600


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "data" / "uploads").mkdir(parents=True)
    return Settings(DATASET_DIR=tmp_path / "data")


def make_dataset(settings, expires_at, with_meta=True):
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


def age(path, seconds_old):
    stamp = NOW.timestamp() - seconds_old
    os.utime(path, (stamp, stamp), follow_symlinks=False)


def names(directory):
    return sorted(p.name for p in directory.iterdir())


def test_expired_live_and_unreadable_datasets(settings):
    expired = make_dataset(settings, NOW - timedelta(minutes=1))
    live = make_dataset(settings, NOW + timedelta(hours=1))
    broken = settings.dataset_dir / f"{new_dataset_id()}.duckdb"
    broken.write_bytes(b"this is not a duckdb file" * 100)

    result = sweep(settings, NOW)

    assert names(settings.dataset_dir) == sorted(["uploads", live.name])
    assert result.datasets_removed == 2
    assert not expired.exists() and not broken.exists()


def test_wal_is_removed_with_its_dataset_and_kept_with_a_live_one(settings):
    expired = make_dataset(settings, NOW - timedelta(hours=1))
    live = make_dataset(settings, NOW + timedelta(hours=1))
    expired_wal = expired.with_name(expired.name + ".wal")
    live_wal = live.with_name(live.name + ".wal")
    expired_wal.write_bytes(b"wal")
    live_wal.write_bytes(b"wal")
    before = (live.read_bytes(), live.stat().st_mtime_ns, live_wal.stat().st_mtime_ns)

    sweep(settings, NOW)

    assert not expired.exists() and not expired_wal.exists()
    assert (live.read_bytes(), live.stat().st_mtime_ns, live_wal.stat().st_mtime_ns) == before
    assert live_wal.read_bytes() == b"wal"


def test_expiry_exactly_now_is_expired_one_second_later_is_not(settings):
    at_now = make_dataset(settings, NOW)
    later = make_dataset(settings, NOW + timedelta(seconds=1))

    sweep(settings, NOW)

    assert not at_now.exists()
    assert later.exists()


def test_dataset_without_meta_table_or_row_is_removed(settings):
    no_row = make_dataset(settings, NOW, with_meta=False)
    no_table = settings.dataset_dir / f"{new_dataset_id()}.duckdb"
    connection = duckdb.connect(str(no_table))
    connection.execute("CREATE TABLE other (x INTEGER)")
    connection.close()

    sweep(settings, NOW)

    assert not no_row.exists() and not no_table.exists()


def test_file_that_vanishes_is_skipped_and_not_counted(settings, monkeypatch):
    gone = make_dataset(settings, NOW - timedelta(hours=1))

    def vanish(path):
        Path(path).unlink()
        raise FileNotFoundError(path)

    monkeypatch.setattr(cleanup, "open_dataset_readonly", vanish)

    result = sweep(settings, NOW)

    assert not gone.exists()
    assert result.datasets_removed == 0


@pytest.mark.parametrize("seconds_old, survives", [(HOUR - 1, True), (HOUR + 1, False)])
def test_orphan_wal_and_importing_files_follow_the_one_hour_rule(settings, seconds_old, survives):
    dataset_id = new_dataset_id()
    entries = [
        settings.dataset_dir / f"{dataset_id}.duckdb.wal",
        settings.dataset_dir / f".{dataset_id}.duckdb.importing",
        settings.dataset_dir / f".{dataset_id}.duckdb.importing.wal",
    ]
    for entry in entries:
        entry.write_bytes(b"x")
        age(entry, seconds_old)

    result = sweep(settings, NOW)

    assert [e.exists() for e in entries] == [survives] * 3
    assert result.temp_files_removed == (0 if survives else 3)


@pytest.mark.parametrize("seconds_old, survives", [(HOUR - 1, True), (HOUR + 1, False)])
def test_uploads_entries_follow_the_one_hour_rule(settings, seconds_old, survives):
    uploads = settings.dataset_dir / "uploads"
    csv = uploads / ("a" * 32 + ".csv")
    csv.write_bytes(b"a,b")
    staging = uploads / ".staging-abc"
    staging.mkdir()
    (staging / "part.parquet").write_bytes(b"x")
    age(csv, seconds_old)
    age(staging / "part.parquet", seconds_old)
    age(staging, seconds_old)

    sweep(settings, NOW)

    assert csv.exists() is survives
    assert staging.exists() is survives


def test_orphan_wal_next_to_a_dataset_is_left_to_the_dataset_rule(settings):
    live = make_dataset(settings, NOW + timedelta(hours=1))
    wal = live.with_name(live.name + ".wal")
    wal.write_bytes(b"wal")
    age(wal, 5 * HOUR)

    sweep(settings, NOW)

    assert wal.exists()


def test_unrelated_entries_are_left_alone(settings):
    directory = settings.dataset_dir
    other = [
        directory / "notes.txt",
        directory / "short.duckdb",
        directory / f"{new_dataset_id()}.duckdb.bak",
        directory / f"x{new_dataset_id()}.duckdb.wal",
        directory / "uploads" / "keep.txt",
    ]
    for path in other:
        path.write_bytes(b"x")
        age(path, 10 * HOUR)
    subdir = directory / "some-dir"
    subdir.mkdir()
    (subdir / f"{new_dataset_id()}.duckdb").write_bytes(b"x")
    age(subdir, 10 * HOUR)

    sweep(settings, NOW)

    assert all(path.exists() for path in other)
    assert (subdir / next(subdir.iterdir()).name).exists()


def test_symlinks_are_never_followed_or_deleted(settings, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target_file = outside / "precious.txt"
    target_file.write_text("keep")
    target_dir = outside / "dir"
    target_dir.mkdir()
    (target_dir / "inner").write_text("keep")
    dataset_id = new_dataset_id()
    links = [
        settings.dataset_dir / f"{dataset_id}.duckdb",
        settings.dataset_dir / f"{new_dataset_id()}.duckdb.wal",
        settings.dataset_dir / f".{new_dataset_id()}.duckdb.importing",
        settings.dataset_dir / "uploads" / ("b" * 32 + ".csv"),
        settings.dataset_dir / "uploads" / ".staging-link",
    ]
    for link in links:
        link.symlink_to(
            target_file if link.suffix != "" and "staging" not in link.name else target_dir
        )
        age(link, 10 * HOUR)

    sweep(settings, NOW)

    assert all(link.is_symlink() for link in links)
    assert target_file.read_text() == "keep"
    assert (target_dir / "inner").read_text() == "keep"


def test_staging_directory_containing_a_symlink_is_left_alone(settings, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("keep")
    staging = settings.dataset_dir / "uploads" / ".staging-x"
    staging.mkdir()
    (staging / "link").symlink_to(outside)
    age(staging, 10 * HOUR)

    sweep(settings, NOW)

    assert (staging / "link").is_symlink()
    assert outside.read_text() == "keep"


def test_dataset_named_entry_that_is_a_directory_or_symlink_is_ignored(settings, tmp_path):
    as_dir = settings.dataset_dir / f"{new_dataset_id()}.duckdb"
    as_dir.mkdir()
    real = make_dataset(settings, NOW - timedelta(hours=1))
    moved = tmp_path / "moved.duckdb"
    real.rename(moved)
    linked = settings.dataset_dir / real.name
    linked.symlink_to(moved)

    sweep(settings, NOW)

    assert as_dir.is_dir()
    assert linked.is_symlink() and moved.exists()


def test_sweep_continues_after_an_undeletable_file(settings, monkeypatch, caplog):
    first = make_dataset(settings, NOW - timedelta(hours=1))
    second = make_dataset(settings, NOW - timedelta(hours=1))
    original = Path.unlink

    def flaky(self, *args, **kwargs):
        if self.name == first.name:
            raise PermissionError("nope")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky)
    with caplog.at_level(logging.INFO, logger="app.cleanup"):
        result = sweep(settings, NOW)

    assert first.exists() and not second.exists()
    assert result.datasets_removed == 1
    assert any(
        first.name in r.getMessage() and "PermissionError" in r.getMessage() for r in caplog.records
    )


def test_sweep_logs_one_info_line_with_counts_only(settings, caplog):
    expired = make_dataset(settings, NOW - timedelta(hours=1))
    old_csv = settings.dataset_dir / "uploads" / ("c" * 32 + ".csv")
    old_csv.write_bytes(b"x")
    age(old_csv, 5 * HOUR)

    with caplog.at_level(logging.INFO, logger="app.cleanup"):
        sweep(settings, NOW)

    records = [r for r in caplog.records if r.name == "app.cleanup"]
    assert len(records) == 1 and records[0].levelno == logging.INFO
    message = records[0].getMessage()
    assert "1 datasets" in message and "1 temporary" in message
    assert expired.name not in message and old_csv.name not in message


def test_sweep_without_uploads_directory(settings):
    (settings.dataset_dir / "uploads").rmdir()

    assert sweep(settings, NOW).temp_files_removed == 0


# --- setting -------------------------------------------------------------------


def test_interval_default_and_override(monkeypatch):
    monkeypatch.delenv("CLEANUP_INTERVAL_MINUTES", raising=False)
    assert Settings().cleanup_interval_minutes == 15
    monkeypatch.setenv("CLEANUP_INTERVAL_MINUTES", "3")
    assert Settings().cleanup_interval_minutes == 3


@pytest.mark.parametrize("raw", ["0", "-5", "abc", "1.5", ""])
def test_invalid_interval_names_the_variable(monkeypatch, raw):
    monkeypatch.setenv("CLEANUP_INTERVAL_MINUTES", raw)

    with pytest.raises(ValidationError, match="CLEANUP_INTERVAL_MINUTES"):
        Settings()


# --- startup directory ---------------------------------------------------------


def test_prepare_creates_missing_directory_with_parents_and_0700(tmp_path):
    target = tmp_path / "a" / "b" / "data"

    prepare_dataset_dir(Settings(DATASET_DIR=target))

    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_prepare_leaves_existing_permissions_alone(tmp_path):
    target = tmp_path / "data"
    target.mkdir()
    target.chmod(0o755)

    prepare_dataset_dir(Settings(DATASET_DIR=target))

    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_prepare_error_names_dataset_dir(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")

    with pytest.raises(RuntimeError, match="DATASET_DIR"):
        prepare_dataset_dir(Settings(DATASET_DIR=blocker / "data"))
    with pytest.raises(RuntimeError, match="DATASET_DIR"):
        prepare_dataset_dir(Settings(DATASET_DIR=blocker))


# --- timer ----------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


def test_loop_sleeps_one_interval_before_the_first_sweep(settings, monkeypatch):
    events = []
    settings = Settings(DATASET_DIR=settings.dataset_dir, CLEANUP_INTERVAL_MINUTES=7)
    monkeypatch.setattr(cleanup, "sweep", lambda s, now: events.append("sweep"))

    async def fake_sleep(seconds):
        events.append(("sleep", seconds))
        if events.count(("sleep", 420)) == 3:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(run_cleanup_loop(settings, sleep=fake_sleep))

    assert events == [("sleep", 420), "sweep", ("sleep", 420), "sweep", ("sleep", 420)]


def test_loop_survives_a_failing_sweep(settings, monkeypatch, caplog):
    calls = []

    def flaky(s, now):
        calls.append(1)
        raise OSError("boom")

    monkeypatch.setattr(cleanup, "sweep", flaky)

    async def fake_sleep(seconds):
        if len(calls) == 2:
            raise asyncio.CancelledError

    with caplog.at_level(logging.ERROR, logger="app.cleanup"):
        with pytest.raises(asyncio.CancelledError):
            run(run_cleanup_loop(settings, sleep=fake_sleep))

    assert len(calls) == 2
    assert any("OSError" in r.getMessage() for r in caplog.records)


def test_sweep_runs_in_a_worker_thread(settings, monkeypatch):
    import threading

    seen = {}
    monkeypatch.setattr(cleanup, "sweep", lambda s, now: seen.update(t=threading.current_thread()))

    async def go():
        seen["main"] = threading.current_thread()
        await run_sweep_safely(settings)

    run(go())

    assert seen["t"] is not seen["main"]


# --- lifespan -------------------------------------------------------------------


@pytest.fixture
def env_dir(tmp_path, monkeypatch):
    target = tmp_path / "env-data"
    monkeypatch.setenv("DATASET_DIR", str(target))
    get_settings.cache_clear()
    yield target
    get_settings.cache_clear()


def test_startup_creates_directory_and_sweeps_before_serving(env_dir):
    settings = Settings()
    prepare_dataset_dir(settings)
    expired = make_dataset(settings, datetime.now(UTC) - timedelta(minutes=1))
    live = make_dataset(settings, datetime.now(UTC) + timedelta(hours=1))

    with TestClient(app) as client:
        assert not expired.exists() and live.exists()
        assert client.get("/api/health").status_code == 200


def test_startup_creates_missing_directory(env_dir):
    with TestClient(app):
        assert stat.S_IMODE(env_dir.stat().st_mode) == 0o700


def test_startup_fails_naming_dataset_dir_when_it_cannot_be_created(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("DATASET_DIR", str(blocker))
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DATASET_DIR"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()


def test_startup_survives_a_failing_first_sweep_and_timer_is_cancelled(
    env_dir, monkeypatch, caplog
):
    def boom(s, now):
        raise OSError("boom")

    monkeypatch.setattr(cleanup, "sweep", boom)
    with caplog.at_level(logging.ERROR, logger="app.cleanup"):
        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200

    assert any("OSError" in r.getMessage() for r in caplog.records)


def test_invalid_interval_stops_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("CLEANUP_INTERVAL_MINUTES", "0")
    get_settings.cache_clear()
    try:
        with pytest.raises(Exception, match="CLEANUP_INTERVAL_MINUTES"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()
