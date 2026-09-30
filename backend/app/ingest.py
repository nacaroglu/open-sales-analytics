import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.currencies import is_valid_currency
from app.importer import dataset_path, import_dataset
from app.meta import read_meta
from app.schema import open_dataset_readonly
from app.tokens import hash_token, new_dataset_id, new_token
from app.validation import ValidationResult, stage_csv, validate_rows, validate_structure


@dataclass
class CreatedDataset:
    dataset_id: str
    token: str
    meta: dict
    warnings: list[dict] = field(default_factory=list)


def new_upload_path(settings: Settings) -> Path:
    """A fresh server-named file path in ``<DATASET_DIR>/uploads/``, folders made 0700.

    The file itself is not created. No client-supplied text is used.
    """
    for folder in (settings.dataset_dir, settings.dataset_dir / "uploads"):
        if not folder.exists():
            folder.mkdir()
            folder.chmod(0o700)
    return settings.dataset_dir / "uploads" / f"{secrets.token_hex(16)}.csv"


def ingest_csv(
    csv_path: str | os.PathLike[str],
    currency: str,
    settings: Settings,
    now: datetime | None = None,
) -> CreatedDataset | ValidationResult:
    """Validate an uploaded CSV and, if it is clean, turn it into a dataset.

    Returns ``CreatedDataset`` on success, or the ``ValidationResult`` with
    every error found (structure errors alone if the structure is bad). Its
    warnings include those of the structure check. Either way the CSV is
    deleted and no staging connection is left open. If anything else goes
    wrong the exception propagates, no dataset file is left for the new ID,
    and the CSV is still deleted. Assumes ``currency`` is one of ``CURRENCIES``.
    """
    csv_path = Path(csv_path)
    if not is_valid_currency(currency):
        csv_path.unlink(missing_ok=True)
        raise ValueError("unsupported currency")

    staging = None
    try:
        structure = validate_structure(csv_path, settings.max_upload_bytes, settings.max_rows)
        if not structure.ok:
            return _discard(structure, staging, csv_path)

        staging = stage_csv(csv_path)
        rows = validate_rows(staging)
        rows.warnings = structure.warnings + rows.warnings
        if not rows.ok:
            return _discard(rows, staging, csv_path)
    except BaseException:
        _discard(None, staging, csv_path)
        raise

    return _import(staging, csv_path, currency, settings, now, rows.to_dict()["warnings"])


def _discard(result, staging, csv_path: Path):
    """Close the staging connection and delete the CSV; hand back ``result``."""
    try:
        if staging is not None:
            staging.close()
    finally:
        csv_path.unlink(missing_ok=True)
    return result


def _import(staging, csv_path, currency, settings, now, warnings) -> CreatedDataset:
    dataset_id = new_dataset_id()
    token = new_token()
    target = dataset_path(settings, dataset_id)
    try:
        # import_dataset closes the staging connection and deletes the CSV.
        import_dataset(staging, csv_path, dataset_id, currency, hash_token(token), settings, now)
        connection = open_dataset_readonly(target)
        try:
            meta = read_meta(connection)
        finally:
            connection.close()
    except BaseException:
        _discard(None, staging, csv_path)
        for leftover in (target, target.with_name(target.name + ".wal")):
            leftover.unlink(missing_ok=True)
        raise
    return CreatedDataset(dataset_id, token, meta, warnings)
