"""Monthly acquisition-cohort retention with per-cell maturity states."""

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Literal, TypedDict

import duckdb

CellState = Literal["complete", "partial", "not_observed"]


class CohortCell(TypedDict):
    month_offset: int
    state: CellState
    retained_count: int | None


class CohortRow(TypedDict):
    cohort_month: date
    cohort_size: int
    cells: list[CohortCell]


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(month: date, months: int) -> date:
    index = month.year * 12 + month.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def cell_state(cell_month: date, cutoff: date) -> CellState:
    """Maturity of one calendar month against the data cutoff (inclusive)."""
    if cell_month > cutoff:
        return "not_observed"
    last_day = add_months(cell_month, 1) - timedelta(days=1)
    return "complete" if last_day <= cutoff else "partial"


def cohort_grid(
    cohort_months: Iterable[date], start: date, cutoff: date
) -> list[tuple[date, list[tuple[int, CellState]]]]:
    """Select the cohort rows for a range and lay out every cell's maturity state.

    Rows are the given cohort months (first days of months) that overlap the range
    ``[start, cutoff]``, oldest first. Every row has cells ``N = 0`` up to the number of
    months from the oldest returned cohort to the month containing ``cutoff``, so the
    matrix is rectangular; each cell's state compares calendar month ``cohort + N`` with
    ``cutoff``. Pure date arithmetic, never the clock.
    """
    first, last = month_start(start), month_start(cutoff)
    months = sorted({month for month in cohort_months if first <= month <= last})
    if not months:
        return []
    width = _months_between(months[0], last) + 1
    return [
        (
            month,
            [(offset, cell_state(add_months(month, offset), cutoff)) for offset in range(width)],
        )
        for month in months
    ]


def read_cohort_retention(
    connection: duckdb.DuckDBPyConnection, start: date, cutoff: date
) -> list[CohortRow]:
    """Cohort sizes and retained counts for acquisition cohorts overlapping the range.

    A customer's cohort is ``customer_facts.acquisition_month``; customers whose
    ``first_order_date`` is after ``cutoff`` are not members. Month ``N`` retains a
    member with an identified line dated in calendar month ``cohort + N`` and on or
    before ``cutoff``; lines before ``start`` still count. ``not_observed`` cells have
    no count. Only aggregates are returned; customer IDs never leave the SQL.
    """
    first, last = month_start(start), month_start(cutoff)
    sizes = dict(
        connection.execute(
            """
            SELECT acquisition_month, count(*)
            FROM customer_facts
            WHERE first_order_date <= ? AND acquisition_month BETWEEN ? AND ?
            GROUP BY acquisition_month
            """,
            [cutoff, first, last],
        ).fetchall()
    )
    retained = {
        (month, int(offset)): int(count)
        for month, offset, count in connection.execute(
            """
            SELECT cf.acquisition_month,
                   date_diff('month', cf.acquisition_month,
                             CAST(date_trunc('month', li.order_date) AS DATE)) AS month_offset,
                   count(DISTINCT li.customer_id)
            FROM line_items AS li
            JOIN customer_facts AS cf ON cf.customer_id = li.customer_id
            WHERE li.customer_id IS NOT NULL
              AND li.order_date <= ?
              AND cf.first_order_date <= ?
              AND cf.acquisition_month BETWEEN ? AND ?
            GROUP BY 1, 2
            """,
            [cutoff, cutoff, first, last],
        ).fetchall()
    }
    return [
        {
            "cohort_month": month,
            "cohort_size": int(sizes[month]),
            "cells": [
                {
                    "month_offset": offset,
                    "state": state,
                    "retained_count": (
                        None if state == "not_observed" else retained.get((month, offset), 0)
                    ),
                }
                for offset, state in cells
            ],
        }
        for month, cells in cohort_grid(sizes, start, cutoff)
    ]
