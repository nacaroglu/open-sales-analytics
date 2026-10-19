"""Transparent mature-cohort projection of 12-month customer value."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict

import duckdb

from app.analytics.customers.historical_value import (
    CumulativeValueCell,
    CumulativeValueRow,
    read_cumulative_value_by_cohort_age,
)
from app.analytics.customers.projection_eligibility import (
    _cohort_horizon_end,
    evaluate_projection_eligibility,
)
from app.analytics.shared.metrics import PROJECTION_HORIZON_MONTHS

_MONEY_QUANTUM = Decimal("0.0001")


class ProjectionCohort(TypedDict):
    cohort_month: str
    customers: int
    observed_age_months: int
    mature: bool
    observed_per_customer: str
    projected_per_customer: str
    total_per_customer: str


class ProjectionHeadline(TypedDict):
    customers: int
    observed_per_customer: str
    projected_per_customer: str
    total_per_customer: str
    contributing_mature_cohorts: int
    data_cutoff: str


class CustomerProjection(TypedDict):
    cohorts: list[ProjectionCohort]
    headline: ProjectionHeadline


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def _month_offset(cohort_month: date, cutoff: date) -> int:
    return (cutoff.year - cohort_month.year) * 12 + cutoff.month - cohort_month.month


def _monthly_sales(cells: list[CumulativeValueCell]) -> list[Decimal]:
    previous = Decimal(0)
    sales: list[Decimal] = []
    for cell in cells[:PROJECTION_HORIZON_MONTHS]:
        cumulative = cell["cumulative_gross_sales"]
        if cumulative is None:
            break
        cumulative = Decimal(cumulative)
        sales.append(cumulative - previous)
        previous = cumulative
    return sales + [Decimal(0)] * (PROJECTION_HORIZON_MONTHS - len(sales))


def calculate_projection(connection: duckdb.DuckDBPyConnection, cutoff: date) -> CustomerProjection:
    """Calculate the aggregate-only cohort projection without checking eligibility.

    Callers serving the metric must check issue #130 eligibility first. This low-level
    function remains available for small hand-built unit-test datasets.
    """
    first_row = connection.execute("SELECT min(order_date) FROM line_items").fetchone()
    assert first_row is not None and first_row[0] is not None
    rows = read_cumulative_value_by_cohort_age(connection, first_row[0], cutoff)

    prepared: list[tuple[CumulativeValueRow, list[Decimal], int, bool]] = []
    for row in rows:
        cohort_month = row["cohort_month"]
        observed_age_months = min(max(_month_offset(cohort_month, cutoff), 0), 11) + 1
        mature = _cohort_horizon_end(cohort_month) <= cutoff
        prepared.append((row, _monthly_sales(row["cells"]), observed_age_months, mature))

    mature_rows = [item for item in prepared if item[3]]
    increments = [Decimal(0)] * PROJECTION_HORIZON_MONTHS
    mature_customer_count = sum(int(row["cohort_size"]) for row, _, _, _ in mature_rows)
    if mature_customer_count:
        for _, sales, _, _ in mature_rows:
            for age, value in enumerate(sales):
                increments[age] += value
        increments = [value / Decimal(mature_customer_count) for value in increments]

    cohorts: list[ProjectionCohort] = []
    customer_count = sum(int(row["cohort_size"]) for row, _, _, _ in prepared)
    observed_total = Decimal(0)
    projected_total = Decimal(0)
    for row, sales, observed_age_months, mature in prepared:
        customers = int(row["cohort_size"])
        observed = sum(sales[:observed_age_months], Decimal(0)) / Decimal(customers)
        projected = sum(increments[observed_age_months:], Decimal(0))
        total = Decimal(_money(observed)) + Decimal(_money(projected))
        observed_total += Decimal(customers) * observed
        projected_total += Decimal(customers) * projected
        cohorts.append(
            {
                "cohort_month": row["cohort_month"].strftime("%Y-%m"),
                "customers": customers,
                "observed_age_months": observed_age_months,
                "mature": mature,
                "observed_per_customer": _money(observed),
                "projected_per_customer": _money(projected),
                "total_per_customer": _money(total),
            }
        )

    headline_observed = observed_total / Decimal(customer_count) if customer_count else Decimal(0)
    headline_projected = projected_total / Decimal(customer_count) if customer_count else Decimal(0)
    headline_total = Decimal(_money(headline_observed)) + Decimal(_money(headline_projected))
    return {
        "cohorts": cohorts,
        "headline": {
            "customers": customer_count,
            "observed_per_customer": _money(headline_observed),
            "projected_per_customer": _money(headline_projected),
            "total_per_customer": _money(headline_total),
            "contributing_mature_cohorts": len(mature_rows),
            "data_cutoff": cutoff.isoformat(),
        },
    }


def read_projected_customer_value(
    connection: duckdb.DuckDBPyConnection, cutoff: date
) -> CustomerProjection | None:
    """Return a projection only after the dataset passes issue #130 eligibility."""
    if evaluate_projection_eligibility(connection, cutoff)["status"] != "eligible":
        return None
    return calculate_projection(connection, cutoff)
