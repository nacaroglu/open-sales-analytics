import os
import tempfile
from pathlib import Path

import duckdb

from app.api.datasets import SAMPLE_CSV, SAMPLE_CURRENCY
from app.config import Settings
from app.currencies import CURRENCIES


def storage_is_writable(directory: Path) -> bool:
    """Check the configured temporary storage and remove the probe on every path."""
    probe: Path | None = None
    descriptor: int | None = None
    writable = False
    try:
        descriptor, name = tempfile.mkstemp(prefix=".health-storage-", dir=directory)
        probe = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(b"health")
            stream.flush()
        writable = True
    except Exception:
        writable = False
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                writable = False
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                writable = False
    return writable


def duckdb_is_usable(directory: Path) -> bool:
    """Run a minimal DuckDB query in a disposable file and remove it and its WAL."""
    probe: Path | None = None
    connection: duckdb.DuckDBPyConnection | None = None
    usable = False
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".health-duckdb-", suffix=".duckdb", dir=directory
        )
        probe = Path(name)
        os.close(descriptor)
        probe.unlink()
        connection = duckdb.connect(str(probe))
        usable = connection.execute("SELECT 1").fetchone() == (1,)
    except Exception:
        usable = False
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                usable = False
        if probe is not None:
            for path in (probe, probe.with_name(probe.name + ".wal")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    usable = False
    return usable


def sample_assets_are_available() -> bool:
    """Check the bundled sample and its configured currency without exposing paths."""
    if SAMPLE_CURRENCY not in CURRENCIES:
        return False
    try:
        with SAMPLE_CSV.open("rb") as sample:
            return bool(sample.read(1))
    except OSError:
        return False


def readiness_checks(settings: Settings) -> bool:
    """Return whether storage, DuckDB, and bundled sample inputs can serve the app."""
    try:
        upload_directory = settings.dataset_dir / "uploads"
        upload_directory.mkdir(mode=0o700, exist_ok=True)
    except OSError:
        return False
    return all(
        (
            storage_is_writable(settings.dataset_dir),
            storage_is_writable(upload_directory),
            duckdb_is_usable(settings.dataset_dir),
            sample_assets_are_available(),
        )
    )
