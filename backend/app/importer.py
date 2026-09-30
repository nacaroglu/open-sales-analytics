import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from app.config import Settings
from app.schema import create_dataset

_INSERT_LINE_ITEMS = """
INSERT INTO ds.line_items
SELECT order_id,
       CAST(order_date AS DATE),
       product_id,
       product_name,
       CAST(quantity AS INTEGER),
       CAST(unit_price AS DECIMAL(18,4))
FROM staging
ORDER BY row_number
"""

_INSERT_META = """
INSERT INTO ds.dataset_meta
SELECT $id, $currency, $created_at, $expires_at, $token_hash, count(*)
FROM ds.line_items
"""


def dataset_path(settings: Settings, dataset_id: str) -> Path:
    """The dataset file for an ID; the ID must be a plain file-name stem."""
    if not dataset_id or dataset_id != Path(dataset_id).name or dataset_id.startswith("."):
        raise ValueError("dataset_id must be a plain name, not a path")
    return settings.dataset_dir / f"{dataset_id}.duckdb"


def import_dataset(
    staging: duckdb.DuckDBPyConnection,
    csv_path: str | os.PathLike[str],
    dataset_id: str,
    currency: str,
    token_hash: str,
    settings: Settings,
    now: datetime | None = None,
) -> Path:
    """Turn validated staging tables into ``<DATASET_DIR>/<dataset_id>.duckdb``.

    Assumes validation passed; it does not re-validate. Whatever happens, the
    raw CSV at ``csv_path`` is deleted and the staging connection is closed
    before this returns or raises. On failure no file for this dataset ID is
    left behind. The dataset is built under a temporary name and renamed into
    place, so a partial file never appears under its real name.
    """
    try:
        target = dataset_path(settings, dataset_id)
        if target.exists():
            raise FileExistsError(f"dataset {dataset_id} already exists")

        (row_count,) = staging.execute("SELECT count(*) FROM staging").fetchone()
        if row_count == 0:
            raise ValueError("refusing to import a dataset with no rows")

        created_at = now or datetime.now(UTC)
        if created_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        working = target.with_name(f".{target.name}.importing")
        try:
            create_dataset(working)
            _copy_rows(
                staging,
                working,
                dataset_id,
                currency,
                token_hash,
                created_at,
                created_at + timedelta(hours=settings.dataset_ttl_hours),
            )
            working.rename(target)
        except BaseException:
            _remove_with_wal(working)
            raise
        return target
    finally:
        staging.close()
        Path(csv_path).unlink(missing_ok=True)


def _copy_rows(staging, working, dataset_id, currency, token_hash, created_at, expires_at) -> None:
    staging.execute(f"ATTACH '{_quote(working)}' AS ds")
    try:
        staging.execute("BEGIN")
        staging.execute(_INSERT_LINE_ITEMS)
        staging.execute(
            _INSERT_META,
            {
                "id": dataset_id,
                "currency": currency,
                "created_at": created_at,
                "expires_at": expires_at,
                "token_hash": token_hash,
            },
        )
        staging.execute("COMMIT")
    except BaseException:
        staging.execute("ROLLBACK")
        raise
    finally:
        staging.execute("DETACH ds")


def _quote(path: Path) -> str:
    return str(path).replace("'", "''")


def _remove_with_wal(path: Path) -> None:
    for candidate in (path, path.with_name(path.name + ".wal")):
        candidate.unlink(missing_ok=True)
