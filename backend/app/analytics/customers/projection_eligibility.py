"""Eligibility checks for the projected 12-month customer value metric."""

import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal

import duckdb

from app.analytics.shared.metrics import (
    PROJECTION_CONDITION_LABELS,
    PROJECTION_HISTORY_MONTHS,
    PROJECTION_HORIZON_MONTHS,
    PROJECTION_MATURE_COHORTS,
    PROJECTION_MIN_CUSTOMER_COVERAGE,
    PROJECTION_MIN_IDENTIFIED_CUSTOMERS,
)


def _add_months_clamped(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _history_months(first_order_date: date, cutoff: date) -> int:
    if cutoff < first_order_date:
        return 0
    months = (cutoff.year - first_order_date.year) * 12 + cutoff.month - first_order_date.month
    if _add_months_clamped(first_order_date, months) - date.resolution > cutoff:
        months -= 1
    while _add_months_clamped(first_order_date, months + 1) - date.resolution <= cutoff:
        months += 1
    return max(0, months)


def _cohort_horizon_end(month: date) -> date:
    horizon_month = _add_months_clamped(month, PROJECTION_HORIZON_MONTHS - 1)
    return date(
        horizon_month.year,
        horizon_month.month,
        calendar.monthrange(horizon_month.year, horizon_month.month)[1],
    )


def _condition(code: str, actual: object, threshold: object, passed: bool) -> dict:
    return {
        "code": code,
        "label": PROJECTION_CONDITION_LABELS[code],
        "actual": actual,
        "threshold": threshold,
        "passed": passed,
    }


def _display_coverage(coverage: Decimal | None) -> str | None:
    return (
        None if coverage is None else str(coverage.quantize(Decimal("0.0000"), rounding=ROUND_DOWN))
    )


def _has_customer_id(connection: duckdb.DuckDBPyConnection) -> bool:
    metadata_table = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'dataset_meta'"
    ).fetchone()
    assert metadata_table is not None
    if metadata_table[0]:
        metadata_columns = connection.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'dataset_meta' AND column_name = 'has_customer_id'"
        ).fetchone()
        assert metadata_columns is not None
        if metadata_columns[0]:
            flag = connection.execute("SELECT has_customer_id FROM dataset_meta").fetchone()
            assert flag is not None
            return bool(flag[0])
    line_items_column = connection.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = 'line_items' AND column_name = 'customer_id'"
    ).fetchone()
    assert line_items_column is not None
    return bool(line_items_column[0])


def _coverage(connection: duckdb.DuckDBPyConnection, cutoff: date) -> Decimal | None:
    if not _has_customer_id(connection):
        return None
    row = connection.execute(
        """
        SELECT count(*) AS total_orders,
               count(*) FILTER (WHERE identified) AS identified_orders
        FROM (
            SELECT order_id, bool_or(customer_id IS NOT NULL) AS identified
            FROM line_items
            WHERE order_date <= ?
            GROUP BY order_id
        )
        """,
        [cutoff],
    ).fetchone()
    assert row is not None
    total_orders, identified_orders = int(row[0]), int(row[1])
    if total_orders == 0:
        return Decimal("0")
    return Decimal(identified_orders) / Decimal(total_orders)


def evaluate_projection_eligibility(connection: duckdb.DuckDBPyConnection, cutoff: date) -> dict:
    """Evaluate all projection requirements using full history through ``cutoff``.

    The return value contains aggregates only. In particular, no customer identifier or
    cohort membership is selected into Python or included in the response.
    """
    first_row = connection.execute("SELECT min(order_date) FROM line_items").fetchone()
    assert first_row is not None
    first_order_date = first_row[0]
    history_months = _history_months(first_order_date, cutoff)

    if not _has_customer_id(connection):
        identified_customers = 0
        coverage = None
        mature_cohorts = 0
        status = "unavailable"
    else:
        customer_row = connection.execute(
            "SELECT count(*) FROM customer_facts WHERE first_order_date <= ?", [cutoff]
        ).fetchone()
        assert customer_row is not None
        identified_customers = int(customer_row[0])
        coverage = _coverage(connection, cutoff)
        cohort_months = connection.execute(
            """
            SELECT DISTINCT acquisition_month
            FROM customer_facts
            WHERE first_order_date <= ?
            """,
            [cutoff],
        ).fetchall()
        mature_cohorts = sum(_cohort_horizon_end(month) <= cutoff for (month,) in cohort_months)
        status = "eligible"

    coverage_actual = _display_coverage(coverage)
    conditions = [
        _condition(
            "history_months",
            history_months,
            PROJECTION_HISTORY_MONTHS,
            history_months >= PROJECTION_HISTORY_MONTHS,
        ),
        _condition(
            "identified_customers",
            identified_customers,
            PROJECTION_MIN_IDENTIFIED_CUSTOMERS,
            identified_customers >= PROJECTION_MIN_IDENTIFIED_CUSTOMERS,
        ),
        _condition(
            "customer_coverage",
            coverage_actual,
            str(PROJECTION_MIN_CUSTOMER_COVERAGE),
            coverage is not None and coverage >= PROJECTION_MIN_CUSTOMER_COVERAGE,
        ),
        _condition(
            "mature_cohorts",
            mature_cohorts,
            PROJECTION_MATURE_COHORTS,
            mature_cohorts >= PROJECTION_MATURE_COHORTS,
        ),
    ]
    if status != "unavailable":
        status = (
            "eligible" if all(condition["passed"] for condition in conditions) else "ineligible"
        )
    return {"status": status, "data_cutoff": cutoff.isoformat(), "conditions": conditions}
