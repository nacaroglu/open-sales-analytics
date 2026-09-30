import duckdb

# Timestamps are formatted in SQL: DuckDB cannot hand a TIMESTAMPTZ to Python
# without the pytz package, which is not a dependency.
_TIMESTAMP = "'%Y-%m-%dT%H:%M:%SZ'"
_META_SQL = f"""
SELECT id,
       currency,
       strftime(created_at AT TIME ZONE 'UTC', {_TIMESTAMP}),
       strftime(expires_at AT TIME ZONE 'UTC', {_TIMESTAMP}),
       row_count
FROM dataset_meta
"""
_DATE_RANGE_SQL = """
SELECT strftime(min(order_date), '%Y-%m-%d'), strftime(max(order_date), '%Y-%m-%d')
FROM line_items
"""


def read_meta(connection: duckdb.DuckDBPyConnection) -> dict:
    """The public metadata of the dataset behind an open connection.

    Returns ``{"id", "currency", "created_at", "expires_at", "row_count",
    "date_range": {"min", "max"}}`` with UTC timestamps like
    ``2026-09-30T12:19:11Z`` and ``YYYY-MM-DD`` dates. It never includes the
    token hash. Raises ``LookupError`` if the file has no metadata row.
    """
    row = connection.execute(_META_SQL).fetchone()
    if row is None:
        raise LookupError("the dataset has no metadata row")
    dataset_id, currency, created_at, expires_at, row_count = row
    date_range = connection.execute(_DATE_RANGE_SQL).fetchone()
    assert date_range is not None  # an aggregate query always returns one row
    first, last = date_range
    return {
        "id": dataset_id,
        "currency": currency,
        "created_at": created_at,
        "expires_at": expires_at,
        "row_count": row_count,
        "date_range": {"min": first, "max": last},
    }
