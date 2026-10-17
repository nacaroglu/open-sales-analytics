import csv
import os
import shutil
import tempfile
from pathlib import Path

import duckdb

from app.validation.structure import OPTIONAL_COLUMNS, REQUIRED_COLUMNS

# A value that cannot occur in the normalised temp file, so DuckDB never turns
# an empty string into NULL.
_NULL_SENTINEL = "\x01<null>\x01"


def stage_csv(path: str | os.PathLike[str]) -> duckdb.DuckDBPyConnection:
    """Load a CSV into an in-memory DuckDB database and return the connection.

    Two tables are created:

    * ``staging`` - one row per data record, every column ``VARCHAR`` (nothing
      is inferred, so ``007`` stays ``007``) plus ``row_number``. The six
      required columns and optional ``customer_id`` are read; values are
      trimmed of surrounding whitespace and blank values become SQL ``NULL``.
    * ``staging_meta`` - one row recording whether the input header contained
      the optional ``customer_id`` column.
    * ``staging_malformed`` - ``row_number, field_count, header_field_count``
      for records whose field count differs from the header's. They cannot be
      mapped to columns, so they are not in ``staging``.

    ``row_number`` is the record's position with the header as row 1. Blank
    lines take up a number but are not rows. A quoted value containing a line
    break is still one record.

    Assumes ``validate_structure`` has passed: the six headers are present once
    and the file is UTF-8. The caller owns closing the connection.

    The parsed values are bulk-loaded through a normalised temporary CSV in a
    private directory next to the input; it is deleted before this returns.
    Loading row by row through the Python API is orders of magnitude slower.
    """
    path = Path(path)
    workdir = Path(tempfile.mkdtemp(prefix=".staging-", dir=path.parent))
    try:
        rows_file = workdir / "rows.csv"
        bad_file = workdir / "malformed.csv"
        has_customer_id = _normalise(path, rows_file, bad_file)

        connection = duckdb.connect(":memory:")
        connection.execute(_STAGING_SQL, [str(rows_file)])
        connection.execute(_MALFORMED_SQL, [str(bad_file)])
        connection.execute("CREATE TABLE staging_meta (has_customer_id BOOLEAN NOT NULL)")
        connection.execute("INSERT INTO staging_meta VALUES (?)", [has_customer_id])
        return connection
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _normalise(path: Path, rows_file: Path, bad_file: Path) -> bool:
    with (
        open(path, encoding="utf-8-sig", newline="") as source,
        open(rows_file, "w", encoding="utf-8", newline="") as rows_out,
        open(bad_file, "w", encoding="utf-8", newline="") as bad_out,
    ):
        rows = csv.writer(rows_out, quoting=csv.QUOTE_ALL, lineterminator="\n")
        bad = csv.writer(bad_out, lineterminator="\n")

        header: list[str] | None = None
        indexes: list[int] = []
        has_customer_id = False
        record_number = 0
        for record in csv.reader(source):
            if header is None:
                if not record:
                    continue  # blank lines before the header do not count
                header = [name.strip() for name in record]
                indexes = _column_indexes(header)
                has_customer_id = "customer_id" in header
                record_number = 1
                continue
            record_number += 1
            if not record:
                continue
            if len(record) != len(header):
                bad.writerow([record_number, len(record), len(header)])
                continue
            values = []
            for column, index in zip((*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS), indexes, strict=True):
                if index == -1:
                    values.append(_NULL_SENTINEL)
                    continue
                value = record[index].strip()
                values.append(_NULL_SENTINEL if column == "customer_id" and value == "" else value)
            rows.writerow([record_number, *values])

    if header is None:
        raise ValueError("the file has no header row")
    return has_customer_id


def _column_indexes(header: list[str]) -> list[int]:
    indexes = []
    for column in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS):
        if column == "customer_id" and header.count(column) == 0:
            indexes.append(-1)
            continue
        if header.count(column) != 1:
            raise ValueError(
                f"column {column!r} must appear exactly once; run validate_structure first"
            )
        indexes.append(header.index(column))
    return indexes


def _read_csv(columns: str) -> str:
    return (
        "read_csv(?, header=false, auto_detect=false, delim=',', quote='\"', "
        f"escape='\"', nullstr='{_NULL_SENTINEL}', columns={{{columns}}})"
    )


_STAGING_SQL = (
    "CREATE TABLE staging AS SELECT CAST(row_number AS BIGINT) AS row_number, "
    + ", ".join((*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS))
    + " FROM "
    + _read_csv(
        ", ".join(f"'{c}': 'VARCHAR'" for c in ("row_number", *REQUIRED_COLUMNS, *OPTIONAL_COLUMNS))
    )
)

_MALFORMED_SQL = (
    "CREATE TABLE staging_malformed AS SELECT CAST(row_number AS BIGINT) AS row_number, "
    "CAST(field_count AS INTEGER) AS field_count, "
    "CAST(header_field_count AS INTEGER) AS header_field_count FROM "
    + _read_csv(
        "'row_number': 'VARCHAR', 'field_count': 'VARCHAR', 'header_field_count': 'VARCHAR'"
    )
)
