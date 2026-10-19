"""Observed Historical Customer Value per acquired customer, by acquisition cohort age."""

from datetime import date
from decimal import Decimal
from typing import TypedDict

import duckdb

from app.analytics.customers.cohort_retention import CellState, cohort_grid, month_start

# Member filter shared with read_cohort_retention (same parameters: cutoff, first, last).
_MEMBERS = "cf.first_order_date <= ? AND cf.acquisition_month BETWEEN ? AND ?"


class CumulativeValueCell(TypedDict):
    month_offset: int
    state: CellState
    cumulative_gross_sales: Decimal | None


class CumulativeValueRow(TypedDict):
    cohort_month: date
    cohort_size: int
    cells: list[CumulativeValueCell]


class HistoricalCustomerValue(TypedDict):
    customer_count: int
    total_value: Decimal
    median: Decimal | None
    rows: list[CumulativeValueRow]


def _member_params(start: date, cutoff: date) -> list[date]:
    return [cutoff, month_start(start), month_start(cutoff)]


def read_cumulative_value_by_cohort_age(
    connection: duckdb.DuckDBPyConnection, start: date, cutoff: date
) -> list[CumulativeValueRow]:
    """Observed cumulative identified gross sales per cohort and month offset.

    Rows and cell states are those of ``read_cohort_retention`` for the same range: the
    members are identified customers whose ``acquisition_month`` overlaps the range and
    whose ``first_order_date`` is on or before ``cutoff``. A cell holds the cohort's gross
    sales (``quantity * unit_price``) from the acquisition month through the end of
    calendar month ``cohort + N``, capped at ``cutoff``; ``not_observed`` cells are
    ``None``. Only aggregates are returned; customer IDs never leave the SQL.
    """
    sizes = dict(
        connection.execute(
            "SELECT cf.acquisition_month, count(*) FROM customer_facts AS cf "
            f"WHERE {_MEMBERS} GROUP BY 1",
            _member_params(start, cutoff),
        ).fetchall()
    )
    monthly = {
        (month, int(offset)): Decimal(sales)
        for month, offset, sales in connection.execute(
            f"""
            SELECT cf.acquisition_month,
                   date_diff('month', cf.acquisition_month,
                             CAST(date_trunc('month', li.order_date) AS DATE)),
                   sum(li.quantity * li.unit_price)
            FROM line_items AS li
            JOIN customer_facts AS cf ON cf.customer_id = li.customer_id
            WHERE {_MEMBERS}
              AND li.customer_id IS NOT NULL
              AND li.order_date <= ?
            GROUP BY 1, 2
            """,
            [*_member_params(start, cutoff), cutoff],
        ).fetchall()
    }
    rows: list[CumulativeValueRow] = []
    for month, grid in cohort_grid(sizes, start, cutoff):
        running = Decimal(0)
        cells: list[CumulativeValueCell] = []
        for offset, state in grid:
            running += monthly.get((month, offset), Decimal(0))
            cells.append(
                {
                    "month_offset": offset,
                    "state": state,
                    "cumulative_gross_sales": None if state == "not_observed" else running,
                }
            )
        rows.append({"cohort_month": month, "cohort_size": int(sizes[month]), "cells": cells})
    return rows


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def read_historical_customer_value(
    connection: duckdb.DuckDBPyConnection, start: date, cutoff: date
) -> HistoricalCustomerValue:
    """Count, total and median of observed per-customer value, plus the cohort-age grid.

    A member's value is their identified gross sales dated on or before ``cutoff``,
    including lines before ``start``. The median is computed from an anonymous, sorted
    list of values.
    """
    values = [
        Decimal(value)
        for (value,) in connection.execute(
            f"""
            SELECT coalesce(sum(li.quantity * li.unit_price), 0) AS value
            FROM line_items AS li
            JOIN customer_facts AS cf ON cf.customer_id = li.customer_id
            WHERE {_MEMBERS}
              AND li.customer_id IS NOT NULL
              AND li.order_date <= ?
            GROUP BY cf.customer_id
            ORDER BY value
            """,
            [*_member_params(start, cutoff), cutoff],
        ).fetchall()
    ]
    return {
        "customer_count": len(values),
        "total_value": sum(values, Decimal(0)),
        "median": _median(values),
        "rows": read_cumulative_value_by_cohort_age(connection, start, cutoff),
    }
