from datetime import date

import duckdb

from app.analytics.shared.periods import _previous_calendar_year

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
_FACT_COUNTS_SQL = """
SELECT
    (SELECT count(*) FROM order_facts),
    (SELECT count(*) FROM product_facts)
"""


def _availability(state: str, reason: str | None = None) -> dict[str, str | None]:
    return {"state": state, "reason": reason}


def _capabilities(
    connection: duckdb.DuckDBPyConnection, first: str, last: str, row_count: int
) -> dict:
    fact_counts = connection.execute(_FACT_COUNTS_SQL).fetchone()
    assert fact_counts is not None
    order_count, product_count = fact_counts
    first_day = date.fromisoformat(first)
    last_day = date.fromisoformat(last)

    previous_period = (
        _availability("available")
        if last_day > first_day
        else _availability("insufficient_data", "A comparison needs at least two days of history.")
    )
    first_previous_year = _previous_calendar_year(last_day)
    previous_year = (
        _availability("available")
        if first_previous_year >= first_day
        else _availability(
            "insufficient_data",
            f"The comparison needs data from {first_previous_year}, but the dataset starts on {first_day}.",
        )
    )
    return {
        "columns": {"customer_id": False},
        "counts": {
            "orders": order_count,
            "products": product_count,
            "line_items": row_count,
            "history_days": (last_day - first_day).days + 1,
        },
        "modules": {
            "overview": _availability("available"),
            "products": _availability("available"),
            "customers": _availability(
                "unavailable",
                "Customer analytics needs an optional customer_id column, which is not supported yet.",
            ),
        },
        "comparisons": {
            "previous_period": previous_period,
            "previous_year": previous_year,
        },
    }


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
    capabilities = _capabilities(connection, first, last, row_count)
    return {
        "id": dataset_id,
        "currency": currency,
        "created_at": created_at,
        "expires_at": expires_at,
        "row_count": row_count,
        "date_range": {"min": first, "max": last},
        "capabilities": capabilities,
    }
