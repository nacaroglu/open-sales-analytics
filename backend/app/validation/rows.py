from datetime import UTC, date, datetime

import duckdb

from app.validation.result import MAX_REPORTED_ERRORS, Issue, ValidationResult
from app.validation.structure import REQUIRED_COLUMNS

MAX_QUANTITY = 2_147_483_647
MAX_PRICE_INTEGER_DIGITS = 14  # DECIMAL(18,4)
MAX_PRICE_DECIMALS = 4
_SHOWN = 40  # characters of an offending value quoted in a reason

_DATE_SHAPE = "regexp_full_match(order_date, '[0-9]{4}-[0-9]{2}-[0-9]{2}')"
_PRICE_SHAPE = "regexp_full_match(unit_price, '-?[0-9]+([.][0-9]+)?')"
_PRICE_INTEGER_DIGITS = "length(regexp_extract(unit_price, '^-?([0-9]+)', 1))"
_PRICE_DECIMALS = "length(regexp_extract(unit_price, '[.]([0-9]+)$', 1))"
_PRICE_ROUNDED_OK = (
    f"{_PRICE_SHAPE} AND {_PRICE_INTEGER_DIGITS} <= {MAX_PRICE_INTEGER_DIGITS} "
    f"AND {_PRICE_DECIMALS} <= {MAX_PRICE_DECIMALS}"
)


def _shown(column: str) -> str:
    return f"'''' || left({column}, {_SHOWN}) || ''''"


# (field, code, condition, reason expression). Every condition other than
# missing_value only applies to non-blank values, so a field gets one error.
_CHECKS: list[tuple[str, str, str, str]] = [
    (column, "missing_value", f"{column} = ''", f"'A value is required for {column}.'")
    for column in REQUIRED_COLUMNS
] + [
    (
        "order_date",
        "invalid_date",
        f"order_date <> '' AND (NOT {_DATE_SHAPE} OR TRY_CAST(order_date AS DATE) IS NULL)",
        f"'Expected a real date written YYYY-MM-DD, got ' || {_shown('order_date')} || '.'",
    ),
    (
        "order_date",
        "future_date",
        f"order_date <> '' AND {_DATE_SHAPE} AND TRY_CAST(order_date AS DATE) > CAST($today AS DATE)",
        "'The order date ' || order_date || ' is in the future.'",
    ),
    (
        "quantity",
        "invalid_quantity",
        "quantity <> '' AND (NOT regexp_full_match(quantity, '[0-9]+') "
        "OR TRY_CAST(quantity AS BIGINT) IS NULL "
        f"OR TRY_CAST(quantity AS BIGINT) NOT BETWEEN 1 AND {MAX_QUANTITY})",
        f"'Expected a whole number from 1 to {MAX_QUANTITY:,}, got ' || {_shown('quantity')} || '.'",
    ),
    (
        "unit_price",
        "invalid_price",
        f"unit_price <> '' AND NOT ({_PRICE_ROUNDED_OK})",
        f"'Expected a plain decimal number with at most {MAX_PRICE_INTEGER_DIGITS} digits before and "
        f"{MAX_PRICE_DECIMALS} after the point, got ' || {_shown('unit_price')} || '.'",
    ),
    (
        "unit_price",
        "negative_price",
        f"unit_price <> '' AND ({_PRICE_ROUNDED_OK}) AND CAST(unit_price AS DECIMAL(18,4)) < 0",
        f"'The unit price must not be negative, got ' || {_shown('unit_price')} || '.'",
    ),
]


def _select(field: str, code: str, condition: str, reason: str) -> str:
    position = REQUIRED_COLUMNS.index(field) + 1
    return (
        f"SELECT row_number, {position} AS position, '{field}' AS field, '{code}' AS code, "
        f"{reason} AS reason FROM staging WHERE {condition}"
    )


# Cross-row rules. Rows with a blank ID or name are skipped: the row-level
# check has already reported them.
_DUPLICATE_LINE_SQL = """
SELECT row_number, 0 AS position, NULL AS field, 'duplicate_line' AS code,
       'This order and product already appear on row ' || first_row || '.' AS reason
FROM (
    SELECT row_number,
           min(row_number) OVER (PARTITION BY order_id, product_id) AS first_row
    FROM staging
    WHERE order_id <> '' AND product_id <> ''
)
WHERE row_number > first_row
"""

# One error per product ID: on the first row whose name differs from the name
# first seen for that ID, naming the first two names and how many there are.
_CONFLICTING_NAME_SQL = f"""
SELECT conflict.row_number, 4 AS position, 'product_name' AS field,
       'conflicting_product_name' AS code,
       'Product ' || {_shown("conflict.product_id")} || ' has ' || conflict.name_count
       || ' different names; the first two are ' || {_shown("conflict.first_name")}
       || ' and ' || {_shown("conflict.second_name")} || '.' AS reason
FROM (
    SELECT s.product_id,
           min(s.row_number) AS row_number,
           any_value(names.first_name) AS first_name,
           arg_min(s.product_name, s.row_number) AS second_name,
           any_value(names.name_count) AS name_count
    FROM staging AS s
    JOIN (
        SELECT product_id,
               arg_min(product_name, row_number) AS first_name,
               count(DISTINCT product_name) AS name_count
        FROM staging
        WHERE product_id <> '' AND product_name <> ''
        GROUP BY product_id
        HAVING count(DISTINCT product_name) > 1
    ) AS names ON s.product_id = names.product_id
    WHERE s.product_name <> '' AND s.product_name <> names.first_name
    GROUP BY s.product_id
) AS conflict
"""

_MALFORMED_ROW_SQL = """
SELECT row_number, 0 AS position, NULL AS field, 'malformed_row' AS code,
       'The row has ' || field_count || ' values but the header has ' || header_field_count
       || '.' AS reason
FROM staging_malformed
"""

_ISSUES_SQL = "CREATE OR REPLACE TEMP TABLE row_issues AS " + " UNION ALL ".join(
    [_select(*check) for check in _CHECKS]
    + [_MALFORMED_ROW_SQL, _DUPLICATE_LINE_SQL, _CONFLICTING_NAME_SQL]
)

_ZERO_PRICE_SQL = (
    f"SELECT count(*) FROM staging WHERE unit_price <> '' AND ({_PRICE_ROUNDED_OK}) "
    "AND CAST(unit_price AS DECIMAL(18,4)) = 0"
)


def validate_rows(
    connection: duckdb.DuckDBPyConnection, today: date | None = None
) -> ValidationResult:
    """Run the row-level and cross-row rules as SQL over the tables made by ``stage_csv``.

    ``today`` is the latest acceptable order date; it defaults to today's date
    in UTC and exists so tests can fix it.
    """
    today = today or datetime.now(UTC).date()
    result = ValidationResult()

    connection.execute(_ISSUES_SQL, {"today": today.isoformat()})
    try:
        count_row = connection.execute("SELECT count(*) FROM row_issues").fetchone()
        assert count_row is not None  # count(*) always returns one row
        (result.error_count,) = count_row
        for row_number, field, code, reason in connection.execute(
            "SELECT row_number, field, code, reason FROM row_issues "
            "ORDER BY row_number, position LIMIT ?",
            [MAX_REPORTED_ERRORS],
        ).fetchall():
            result.errors.append(
                Issue(code=code, reason=reason, row_number=row_number, field=field)
            )
    finally:
        connection.execute("DROP TABLE IF EXISTS row_issues")

    zero_row = connection.execute(_ZERO_PRICE_SQL).fetchone()
    assert zero_row is not None  # an aggregate query always returns one row
    (zero_lines,) = zero_row
    if zero_lines:
        noun = "line has" if zero_lines == 1 else "lines have"
        result.add_warning(
            Issue(
                code="zero_price",
                field="unit_price",
                reason=f"{zero_lines:,} {noun} a unit price of 0.",
            )
        )
    return result
