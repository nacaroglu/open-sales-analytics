import stat
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import Settings
from app.importer import import_dataset
from app.schema import create_dataset, open_dataset_readonly
from app.validation import stage_csv

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
NOW = datetime(2025, 6, 1, 12, 30, tzinfo=UTC)
TOKEN_HASH = "a" * 64


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def settings(data_dir):
    return Settings(DATASET_DIR=data_dir, DATASET_TTL_HOURS=6)


@pytest.fixture
def uploads(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()
    return folder


def write_csv(folder, *rows, header=HEADER):
    path = folder / "upload.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def run_import(uploads, settings, *rows, header=HEADER, dataset_id="abc123", currency="USD", now=NOW):
    path = write_csv(uploads, *rows, header=header)
    staging = stage_csv(path)
    return path, import_dataset(staging, path, dataset_id, currency, TOKEN_HASH, settings, now)


def files_of(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_creates_the_dataset_file_with_typed_rows(uploads, settings, data_dir):
    _, target = run_import(
        uploads, settings,
        "o1,2025-01-02,p1,Mug,2,19.99",
        "o2,2025-01-03,p2,Cup,1,4.5",
    )

    assert target == data_dir / "abc123.duckdb"
    connection = open_dataset_readonly(target)
    rows = connection.execute("SELECT * FROM line_items ORDER BY order_id").fetchall()
    types = [t for _, t in connection.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'line_items' ORDER BY ordinal_position").fetchall()]
    connection.close()
    assert rows == [
        ("o1", date(2025, 1, 2), "p1", "Mug", 2, Decimal("19.9900")),
        ("o2", date(2025, 1, 3), "p2", "Cup", 1, Decimal("4.5000")),
    ]
    assert types == ["VARCHAR", "DATE", "VARCHAR", "VARCHAR", "INTEGER", "DECIMAL(18,4)"]


def test_unit_price_reads_back_exactly(uploads, settings):
    _, target = run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,19.99")

    connection = open_dataset_readonly(target)
    (price,) = connection.execute("SELECT unit_price FROM line_items").fetchone()
    connection.close()

    assert price == Decimal("19.9900") and isinstance(price, Decimal)
    assert str(price) == "19.9900"


def test_text_is_stored_trimmed_and_ids_keep_leading_zeros(uploads, settings):
    _, target = run_import(uploads, settings, " 007 ,2025-01-02, 0042 , Big Mug ,1,1")

    connection = open_dataset_readonly(target)
    row = connection.execute("SELECT order_id, product_id, product_name FROM line_items").fetchone()
    connection.close()

    assert row == ("007", "0042", "Big Mug")


def test_extra_columns_are_not_in_the_dataset_file(uploads, settings):
    _, target = run_import(
        uploads, settings, "o1,2025-01-02,p1,Mug,1,1,SECRET-NOTE",
        header=HEADER + ",notes",
    )

    assert b"SECRET-NOTE" not in target.read_bytes()
    connection = open_dataset_readonly(target)
    names = [r[0] for r in connection.execute(
        "SELECT column_name FROM information_schema.columns").fetchall()]
    connection.close()
    assert "notes" not in names


def test_dataset_meta_has_one_row_with_the_expected_values(uploads, settings):
    _, target = run_import(
        uploads, settings, "o1,2025-01-02,p1,Mug,1,1", "o1,2025-01-02,p2,Cup,1,1", "o2,2025-01-02,p1,Mug,1,1",
        dataset_id="ds-1", currency="EUR",
    )

    connection = open_dataset_readonly(target)
    rows = connection.execute(
        "SELECT id, currency, CAST(epoch(created_at) AS BIGINT), CAST(epoch(expires_at) AS BIGINT), "
        "token_hash, row_count FROM dataset_meta"
    ).fetchall()
    connection.close()

    created = int(NOW.timestamp())
    assert rows == [("ds-1", "EUR", created, created + 6 * 3600, TOKEN_HASH, 3)]


def test_created_at_defaults_to_now_in_utc(uploads, settings):
    before = datetime.now(UTC).replace(microsecond=0)
    _, target = run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1", now=None)

    connection = open_dataset_readonly(target)
    (created,) = connection.execute("SELECT CAST(epoch(created_at) AS BIGINT) FROM dataset_meta").fetchone()
    connection.close()

    assert before.timestamp() <= created <= (before + timedelta(seconds=30)).timestamp()


def test_naive_now_is_rejected_and_leaves_nothing(uploads, settings, data_dir):
    with pytest.raises(ValueError, match="timezone"):
        run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1", now=datetime(2025, 6, 1))

    assert files_of(data_dir) == []


def test_raw_csv_is_deleted_after_success(uploads, settings):
    path, _ = run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1")

    assert not path.exists()
    assert files_of(uploads) == []


def test_only_the_dataset_file_remains_in_the_dataset_dir(uploads, settings, data_dir):
    run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1")

    assert files_of(data_dir) == ["abc123.duckdb"]


def test_dataset_file_is_private_and_opens_read_only(uploads, settings):
    _, target = run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    connection = open_dataset_readonly(target)
    assert connection.execute("SELECT count(*) FROM line_items").fetchone() == (1,)
    connection.close()


def test_many_rows_import_correctly(uploads, settings):
    rows = [f"o{n},2025-01-02,p{n % 7},Mug{n % 7},1,1.25" for n in range(20_000)]

    _, target = run_import(uploads, settings, *rows)

    connection = open_dataset_readonly(target)
    assert connection.execute("SELECT count(*), sum(unit_price) FROM line_items").fetchone() == (
        20_000, Decimal("25000.0000"))
    assert connection.execute("SELECT row_count FROM dataset_meta").fetchone() == (20_000,)
    connection.close()


# --- failures leave no residue -----------------------------------------------


def test_failure_while_inserting_lines_leaves_nothing(uploads, settings, data_dir):
    path = write_csv(uploads, "o1,2025-01-02,p1,Mug,1,1", "o2,2025-01-02,p2,Cup,notanumber,1")

    with pytest.raises(Exception):
        import_dataset(stage_csv(path), path, "abc123", "USD", TOKEN_HASH, settings, NOW)

    assert files_of(data_dir) == []
    assert not path.exists()
    assert files_of(uploads) == []


def test_failure_after_line_items_are_written_leaves_nothing(uploads, settings, data_dir):
    path = write_csv(uploads, "o1,2025-01-02,p1,Mug,1,1")

    # currency=None violates NOT NULL on dataset_meta, after line_items were inserted
    with pytest.raises(Exception):
        import_dataset(stage_csv(path), path, "abc123", None, TOKEN_HASH, settings, NOW)

    assert files_of(data_dir) == []
    assert not path.exists()


def test_existing_dataset_is_left_unchanged(uploads, settings, data_dir):
    _, target = run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1")
    before = target.read_bytes()

    with pytest.raises(FileExistsError):
        run_import(uploads, settings, "o9,2025-02-02,p9,Other,9,9")

    assert target.read_bytes() == before
    assert files_of(data_dir) == ["abc123.duckdb"]
    assert files_of(uploads) == []


def test_a_dataset_with_no_rows_is_never_created(uploads, settings, data_dir):
    path = write_csv(uploads, header=HEADER)  # header only

    with pytest.raises(ValueError, match="no rows"):
        import_dataset(stage_csv(path), path, "abc123", "USD", TOKEN_HASH, settings, NOW)

    assert files_of(data_dir) == []
    assert not path.exists()


@pytest.mark.parametrize("bad_id", ["", "../evil", "a/b", ".hidden", "/abs"])
def test_dataset_id_must_be_a_plain_name(uploads, settings, data_dir, bad_id, tmp_path):
    path = write_csv(uploads, "o1,2025-01-02,p1,Mug,1,1")

    with pytest.raises(ValueError, match="plain name"):
        import_dataset(stage_csv(path), path, bad_id, "USD", TOKEN_HASH, settings, NOW)

    assert files_of(data_dir) == []
    assert not (tmp_path / "evil.duckdb").exists()


def test_uses_the_schema_from_schema_module(uploads, settings, tmp_path):
    reference = tmp_path / "reference.duckdb"
    create_dataset(reference)
    _, target = run_import(uploads, settings, "o1,2025-01-02,p1,Mug,1,1")

    query = ("SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns "
             "ORDER BY table_name, ordinal_position")
    a, b = open_dataset_readonly(reference), open_dataset_readonly(target)
    try:
        assert a.execute(query).fetchall() == b.execute(query).fetchall()
    finally:
        a.close(); b.close()
