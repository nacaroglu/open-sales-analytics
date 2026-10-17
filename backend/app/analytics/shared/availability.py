"""Explicit availability contracts for analytics modules."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

import duckdb

CUSTOMER_COVERAGE_WARNING_PERCENT = 50
CUSTOMER_COVERAGE_NORMAL_PERCENT = 80


class AvailabilityState(StrEnum):
    """The five serialized states used when a module cannot show normal data."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_DATA = "insufficient_data"
    LOW_COVERAGE = "low_coverage"
    ZERO_RESULT = "zero_result"


@dataclass(frozen=True)
class Availability:
    """A state plus the explanation required for every non-available state."""

    state: AvailabilityState
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.state is AvailabilityState.AVAILABLE:
            if self.reason is not None:
                raise ValueError("available state must not have a reason")
        elif not self.reason or not self.reason.strip():
            raise ValueError("non-available states require a nonempty reason")


@dataclass(frozen=True)
class CustomerCoverage:
    """Order-level customer coverage counts and its exact ratio."""

    identified_orders: int
    unidentified_orders: int
    total_orders: int

    @property
    def coverage(self) -> Decimal | None:
        if self.total_orders == 0:
            return None
        return Decimal(self.identified_orders) / Decimal(self.total_orders)


def customer_coverage(
    connection: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
) -> CustomerCoverage:
    """Calculate order-level coverage for the whole dataset or an inclusive range."""
    predicates: list[str] = []
    parameters: list[date] = []
    if start is not None:
        predicates.append("order_date >= ?")
        parameters.append(start)
    if end is not None:
        predicates.append("order_date <= ?")
        parameters.append(end)
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    has_customer_id = connection.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = 'line_items' AND column_name = 'customer_id'"
    ).fetchone()
    assert has_customer_id is not None
    if not has_customer_id[0]:
        row = connection.execute(
            "SELECT count(DISTINCT order_id) FROM line_items"
            + (" WHERE " + " AND ".join(predicates) if predicates else ""),
            parameters,
        ).fetchone()
        assert row is not None
        total_orders = int(row[0])
        return CustomerCoverage(0, total_orders, total_orders)

    row = connection.execute(
        "SELECT count(*) AS total_orders, "
        "count(*) FILTER (WHERE identified) AS identified_orders "
        "FROM (SELECT order_id, bool_or(customer_id IS NOT NULL) AS identified "
        f"FROM line_items{where} GROUP BY order_id)",
        parameters,
    ).fetchone()
    assert row is not None
    total_orders, identified_orders = int(row[0]), int(row[1])
    return CustomerCoverage(identified_orders, total_orders - identified_orders, total_orders)


def customer_coverage_tier(has_customer_id: bool, coverage: CustomerCoverage) -> str:
    """Return the exact whole-dataset customer coverage tier."""
    if not has_customer_id:
        return "missing"
    if coverage.identified_orders * 100 < CUSTOMER_COVERAGE_WARNING_PERCENT * coverage.total_orders:
        return "suppressed"
    if coverage.identified_orders * 100 < CUSTOMER_COVERAGE_NORMAL_PERCENT * coverage.total_orders:
        return "warning"
    return "normal"


def _coverage_percent(coverage: CustomerCoverage) -> int:
    if coverage.total_orders == 0:
        return 0
    return coverage.identified_orders * 100 // coverage.total_orders


def customer_availability(has_customer_id: bool, coverage: CustomerCoverage) -> dict:
    """Map a tier to availability with privacy-safe explanations."""
    tier = customer_coverage_tier(has_customer_id, coverage)
    percent = _coverage_percent(coverage)
    counts = f"{coverage.identified_orders:,} of {coverage.total_orders:,} orders"
    if tier == "missing":
        return {
            "state": AvailabilityState.UNAVAILABLE.value,
            "reason": "The file has no customer_id column.",
        }
    if tier == "suppressed":
        return {
            "state": AvailabilityState.LOW_COVERAGE.value,
            "reason": (
                "Customer analytics needs a customer_id on at least 50% of orders; "
                f"{counts} ({percent}%) have one."
            ),
        }
    if tier == "warning":
        return {
            "state": AvailabilityState.AVAILABLE.value,
            "reason": None,
            "warning": {
                "state": AvailabilityState.LOW_COVERAGE.value,
                "reason": (
                    f"Only {counts} ({percent}%) have a customer_id; "
                    "customer results describe those orders only."
                ),
            },
        }
    return {"state": AvailabilityState.AVAILABLE.value, "reason": None}


def rounded_coverage(coverage: CustomerCoverage) -> Decimal | None:
    """Serialize coverage to four decimal places using half-up rounding."""
    value = coverage.coverage
    return None if value is None else value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
