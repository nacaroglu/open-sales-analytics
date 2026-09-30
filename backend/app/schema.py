import os
from pathlib import Path

import duckdb

LINE_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS line_items (
    order_id     VARCHAR       NOT NULL,
    order_date   DATE          NOT NULL,
    product_id   VARCHAR       NOT NULL,
    product_name VARCHAR       NOT NULL,
    quantity     INTEGER       NOT NULL,
    unit_price   DECIMAL(18,4) NOT NULL
)
"""

DATASET_META_DDL = """
CREATE TABLE IF NOT EXISTS dataset_meta (
    id         VARCHAR     NOT NULL,
    currency   VARCHAR     NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    token_hash VARCHAR     NOT NULL,
    row_count  BIGINT      NOT NULL
)
"""


class DatasetFileError(Exception):
    """The file exists but is not a readable dataset database."""


def create_dataset(path: str | os.PathLike[str]) -> None:
    """Create a dataset file with the canonical tables. Safe to call twice."""
    path = Path(path)
    parent = path.parent
    if not parent.exists():
        parent.mkdir(parents=True)
        parent.chmod(0o700)

    connection = duckdb.connect(str(path))
    try:
        connection.execute(LINE_ITEMS_DDL)
        connection.execute(DATASET_META_DDL)
    finally:
        connection.close()
    path.chmod(0o600)


def open_dataset_readonly(path: str | os.PathLike[str]) -> duckdb.DuckDBPyConnection:
    """Open an existing dataset file read-only."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        return duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:
        raise DatasetFileError(f"not a readable dataset file: {path.name}") from exc
