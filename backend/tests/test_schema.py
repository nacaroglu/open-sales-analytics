import stat
import subprocess
import sys
from decimal import Decimal

import duckdb
import pytest

from app.schema import DatasetFileError, create_dataset, open_dataset_readonly

LINE_ITEMS = [
    ("order_id", "VARCHAR"),
    ("order_date", "DATE"),
    ("product_id", "VARCHAR"),
    ("product_name", "VARCHAR"),
    ("quantity", "INTEGER"),
    ("unit_price", "DECIMAL(18,4)"),
]
DATASET_META = [
    ("id", "VARCHAR"),
    ("currency", "VARCHAR"),
    ("created_at", "TIMESTAMP WITH TIME ZONE"),
    ("expires_at", "TIMESTAMP WITH TIME ZONE"),
    ("token_hash", "VARCHAR"),
    ("row_count", "BIGINT"),
]


@pytest.fixture
def dataset_path(tmp_path):
    return tmp_path / "abc.duckdb"


def columns(connection, table):
    return connection.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()


def test_creates_exactly_the_two_tables(dataset_path):
    create_dataset(dataset_path)

    connection = open_dataset_readonly(dataset_path)
    tables = connection.execute(
        "SELECT table_name FROM information_schema.tables ORDER BY table_name"
    ).fetchall()
    connection.close()
    assert tables == [("dataset_meta",), ("line_items",)]


def test_columns_names_types_and_not_null(dataset_path):
    create_dataset(dataset_path)

    connection = open_dataset_readonly(dataset_path)
    line_items = columns(connection, "line_items")
    dataset_meta = columns(connection, "dataset_meta")
    connection.close()

    assert [(name, kind) for name, kind, _ in line_items] == LINE_ITEMS
    assert [(name, kind) for name, kind, _ in dataset_meta] == DATASET_META
    assert all(nullable == "NO" for *_, nullable in line_items)


def test_unit_price_round_trips_as_exact_decimal(dataset_path):
    create_dataset(dataset_path)
    connection = duckdb.connect(str(dataset_path))
    connection.execute(
        "INSERT INTO line_items VALUES ('o1', DATE '2025-01-02', 'p1', 'Mug', 1, 19.9999)"
    )
    (price,) = connection.execute("SELECT unit_price FROM line_items").fetchone()
    connection.close()

    assert price == Decimal("19.9999")
    assert isinstance(price, Decimal)


def test_create_twice_keeps_existing_rows(dataset_path):
    create_dataset(dataset_path)
    connection = duckdb.connect(str(dataset_path))
    connection.execute("INSERT INTO line_items VALUES ('o1', DATE '2025-01-02', 'p1', 'Mug', 2, 5)")
    connection.close()

    create_dataset(dataset_path)

    connection = open_dataset_readonly(dataset_path)
    assert connection.execute("SELECT count(*) FROM line_items").fetchone() == (1,)
    connection.close()


def test_missing_parent_directory_is_created_private(tmp_path):
    path = tmp_path / "nested" / "abc.duckdb"

    create_dataset(path)

    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_file_is_private(dataset_path):
    create_dataset(dataset_path)

    assert stat.S_IMODE(dataset_path.stat().st_mode) == 0o600


def test_readonly_allows_select_and_rejects_insert(dataset_path):
    create_dataset(dataset_path)
    connection = open_dataset_readonly(dataset_path)

    assert connection.execute("SELECT count(*) FROM line_items").fetchone() == (0,)
    with pytest.raises(duckdb.Error):
        connection.execute(
            "INSERT INTO line_items VALUES ('o1', DATE '2025-01-02', 'p1', 'Mug', 1, 1)"
        )
    connection.close()


def test_opening_missing_path_raises_and_creates_nothing(dataset_path):
    with pytest.raises(FileNotFoundError):
        open_dataset_readonly(dataset_path)

    assert not dataset_path.exists()


def test_opening_a_non_duckdb_file_raises_dataset_file_error(dataset_path):
    dataset_path.write_text("this is not a database, just some text " * 20)

    with pytest.raises(DatasetFileError):
        open_dataset_readonly(dataset_path)


def test_no_connection_is_left_open_after_create(dataset_path):
    create_dataset(dataset_path)

    # A second process can take the write lock only if this one released it.
    result = subprocess.run(
        [sys.executable, "-c", f"import duckdb; duckdb.connect({str(dataset_path)!r}).close()"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    dataset_path.unlink()
    assert not list(dataset_path.parent.glob("abc.duckdb*"))
