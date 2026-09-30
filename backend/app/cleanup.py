import asyncio
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from starlette.concurrency import run_in_threadpool

from app.auth import _EXPIRY_SQL
from app.config import Settings
from app.schema import DatasetFileError, open_dataset_readonly
from app.tokens import is_valid_dataset_id

logger = logging.getLogger("app.cleanup")

# Leftovers younger than this may belong to a request that is still running.
TEMP_FILE_MAX_AGE_SECONDS = 3600

_DATASET_SUFFIX = ".duckdb"
_WAL_SUFFIX = ".duckdb.wal"
_IMPORTING_SUFFIX = ".duckdb.importing"
_IMPORTING_WAL_SUFFIX = ".duckdb.importing.wal"


@dataclass(frozen=True)
class SweepResult:
    datasets_removed: int = 0
    temp_files_removed: int = 0


def prepare_dataset_dir(settings: Settings) -> None:
    """Create DATASET_DIR (0700) if missing; leave an existing one alone."""
    directory = settings.dataset_dir
    try:
        existed = directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if not existed:
            directory.chmod(0o700)
    except OSError as exc:
        raise RuntimeError(
            f"DATASET_DIR {str(directory)!r} cannot be created: {type(exc).__name__}"
        ) from exc


def _id_from(name: str, suffix: str) -> str | None:
    if not name.endswith(suffix):
        return None
    stem = name[: -len(suffix)]
    return stem if is_valid_dataset_id(stem) else None


def _is_plain_file(entry: os.DirEntry) -> bool:
    return entry.is_file(follow_symlinks=False)


def _is_old(path: Path, now: datetime) -> bool:
    try:
        modified = path.lstat().st_mtime
    except OSError:
        return False
    return modified < now.timestamp() - TEMP_FILE_MAX_AGE_SECONDS


def _remove_file(path: Path) -> bool:
    """Delete one file; True only if this call removed it. Never raises."""
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the sweep
        logger.warning("could not remove %s (%s)", path.name, type(exc).__name__)
        return False
    return True


def _remove_tree(path: Path) -> bool:
    """Delete a directory tree unless it holds a symlink (which is never touched)."""
    try:
        for root, dirs, files in os.walk(path, followlinks=False):
            if any(os.path.islink(os.path.join(root, name)) for name in dirs + files):
                return False
        shutil.rmtree(path)
    except FileNotFoundError:
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not remove %s (%s)", path.name, type(exc).__name__)
        return False
    return True


def _is_expired_or_broken(path: Path, now: datetime) -> bool | None:
    """True to delete, False to keep, None if the file vanished."""
    try:
        connection = open_dataset_readonly(path)
    except FileNotFoundError:
        return None
    except (DatasetFileError, duckdb.Error):
        return True if os.path.lexists(path) else None
    try:
        row = connection.execute(_EXPIRY_SQL).fetchone()
        return row is None or row[0] is None or now.timestamp() >= row[0]
    except duckdb.Error:
        return True
    finally:
        connection.close()


def _sweep_datasets_dir(directory: Path, now: datetime) -> tuple[int, int]:
    datasets = temp_files = 0
    with os.scandir(directory) as scan:
        entries = sorted(scan, key=lambda entry: entry.name)
    for entry in entries:
        name = entry.name
        path = directory / name
        if entry.is_symlink() or not _is_plain_file(entry):
            continue
        if _id_from(name, _DATASET_SUFFIX):
            verdict = _is_expired_or_broken(path, now)
            if verdict and _remove_file(path):
                datasets += 1
                _remove_file(path.with_name(name + ".wal"))
        elif _id_from(name, _WAL_SUFFIX):
            if not os.path.lexists(path.with_name(name[: -len(".wal")])) and _is_old(path, now):
                temp_files += _remove_file(path)
        elif name.startswith(".") and (
            _id_from(name[1:], _IMPORTING_SUFFIX) or _id_from(name[1:], _IMPORTING_WAL_SUFFIX)
        ):
            if _is_old(path, now):
                temp_files += _remove_file(path)
    return datasets, temp_files


def _sweep_uploads_dir(directory: Path, now: datetime) -> int:
    try:
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return 0
    removed = 0
    for entry in entries:
        path = directory / entry.name
        if entry.is_symlink() or not _is_old(path, now):
            continue
        if entry.name.startswith(".staging-") and entry.is_dir(follow_symlinks=False):
            removed += _remove_tree(path)
        elif entry.name.endswith(".csv") and entry.is_file(follow_symlinks=False):
            removed += _remove_file(path)
    return removed


def sweep(settings: Settings, now: datetime) -> SweepResult:
    """One cleanup pass over DATASET_DIR; ``now`` must be timezone-aware."""
    datasets, temp_files = _sweep_datasets_dir(settings.dataset_dir, now)
    temp_files += _sweep_uploads_dir(settings.dataset_dir / "uploads", now)
    logger.info(
        "cleanup sweep: %d datasets removed, %d temporary files removed", datasets, temp_files
    )
    return SweepResult(datasets, temp_files)


async def run_sweep_safely(settings: Settings, now: datetime | None = None) -> None:
    """Run one sweep in a worker thread; log instead of raising."""
    try:
        await run_in_threadpool(sweep, settings, now or datetime.now(UTC))
    except Exception as exc:  # noqa: BLE001 - the server and the timer must go on
        logger.error("cleanup sweep failed (%s)", type(exc).__name__)


async def run_cleanup_loop(
    settings: Settings,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Sweep every CLEANUP_INTERVAL_MINUTES, first one a full interval from now."""
    interval = settings.cleanup_interval_minutes * 60
    while True:
        await sleep(interval)
        await run_sweep_safely(settings)
