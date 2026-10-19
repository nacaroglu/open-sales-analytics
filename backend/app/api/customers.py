from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from app.analytics.customers.buckets import DAYS_BETWEEN_PURCHASES_BUCKETS
from app.analytics.customers.coverage import read_customer_coverage
from app.analytics.customers.days_between_purchases import read_days_between_purchases
from app.analytics.customers.identified import read_identified_customer_count
from app.analytics.customers.new_vs_returning import read_new_vs_returning
from app.analytics.customers.repeat_purchase import read_repeat_purchase
from app.analytics.shared.availability import (
    Availability,
    AvailabilityState,
    CustomerCoverage,
    customer_availability,
    customer_coverage_tier,
    rounded_coverage,
)
from app.api.module_common import (
    cache_key,
    cached_json,
    compared,
    compared_ratio,
    comparison_body,
    dataset_expiry,
    ratio,
    resolve_periods,
)
from app.api.module_models import CustomersResponse
from app.auth import AuthorizedDataset, get_now, require_dataset
from app.config import Settings, get_settings
from app.importer import dataset_path
from app.response_cache import ResponseCache, get_response_cache
from app.schema import open_dataset_readonly

router = APIRouter(prefix="/api")


def _dates(meta: dict) -> tuple[date, date]:
    return date.fromisoformat(meta["date_range"]["min"]), date.fromisoformat(
        meta["date_range"]["max"]
    )


def _has_customer_id(meta: dict) -> bool:
    return meta["customer_coverage"]["tier"] != "missing"


def _coverage_body(tier: str, coverage: CustomerCoverage) -> dict:
    rounded = rounded_coverage(coverage)
    return {
        "tier": tier,
        "coverage": None if tier == "missing" or rounded is None else float(rounded),
        "identified_orders": 0 if tier == "missing" else coverage.identified_orders,
        "unidentified_orders": coverage.unidentified_orders,
        "total_orders": coverage.total_orders,
    }


def _availability_body(has_customer_id: bool, coverage: CustomerCoverage) -> dict:
    tier = customer_coverage_tier(has_customer_id, coverage)
    availability = customer_availability(has_customer_id, coverage)
    return {"tier": tier, **availability}


def _identified_customers_body(connection, periods) -> dict:
    current = read_identified_customer_count(connection, periods.current.start, periods.current.end)
    baseline = (
        read_identified_customer_count(
            connection,
            periods.comparison.comparison_start,
            periods.comparison.comparison_end,
        )
        if periods.comparison.available
        else None
    )
    availability = (
        Availability(AvailabilityState.AVAILABLE)
        if current
        else Availability(
            AvailabilityState.ZERO_RESULT,
            "No identified customers placed an order in the selected range.",
        )
    )
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "value": compared(current, baseline, as_money=False),
    }


def _new_vs_returning_body(connection, periods) -> dict:
    current = read_new_vs_returning(connection, periods.current.start, periods.current.end)
    baseline = (
        read_new_vs_returning(
            connection,
            periods.comparison.comparison_start,
            periods.comparison.comparison_end,
        )
        if periods.comparison.available
        else None
    )
    availability = (
        Availability(AvailabilityState.AVAILABLE)
        if current["identified_rows"]
        else Availability(
            AvailabilityState.ZERO_RESULT,
            "No identified customer rows were found in the selected range.",
        )
    )
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "new_customer_gross_sales": compared(
            current["new_customer_gross_sales"],
            None if baseline is None else baseline["new_customer_gross_sales"],
            as_money=True,
        ),
        "returning_customer_gross_sales": compared(
            current["returning_customer_gross_sales"],
            None if baseline is None else baseline["returning_customer_gross_sales"],
            as_money=True,
        ),
        "identified_gross_sales": compared(
            current["identified_gross_sales"],
            None if baseline is None else baseline["identified_gross_sales"],
            as_money=True,
        ),
    }


def _repeat_purchase_body(connection, periods) -> dict:
    current = read_repeat_purchase(connection, periods.current.start, periods.current.end)
    baseline = (
        read_repeat_purchase(
            connection,
            periods.comparison.comparison_start,
            periods.comparison.comparison_end,
        )
        if periods.comparison.available
        else None
    )
    active = current["active_customers"]
    repeat = current["repeat_customers"]
    if not active:
        availability = Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            "No identified customers placed an order in the selected range, "
            "so the repeat-purchase rate is undefined.",
        )
    elif not repeat:
        availability = Availability(
            AvailabilityState.ZERO_RESULT,
            "No active identified customer had two or more orders by the end of the range.",
        )
    else:
        availability = Availability(AvailabilityState.AVAILABLE)
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "active_customers": compared(
            active, None if baseline is None else baseline["active_customers"], as_money=False
        ),
        "repeat_customers": compared(
            repeat, None if baseline is None else baseline["repeat_customers"], as_money=False
        ),
        "repeat_purchase_rate": compared_ratio(
            repeat,
            active,
            None if baseline is None else baseline["repeat_customers"],
            None if baseline is None else baseline["active_customers"],
        ),
    }


def _days_between_purchases_body(connection, periods) -> dict:
    """Current-range only: the section has no comparison values."""
    result = read_days_between_purchases(connection, periods.current.start, periods.current.end)
    total = result["interval_count"]
    availability = (
        Availability(AvailabilityState.AVAILABLE)
        if total
        else Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            "No identified customer placed a repeat order in the selected range, "
            "so there is no interval between purchases.",
        )
    )
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "median_days": result["median_days"],
        "interval_count": total,
        "contributing_customers": result["contributing_customers"],
        "buckets": [
            {
                "key": bucket.key,
                "min_days": bucket.min_days,
                "max_days": bucket.max_days,
                "interval_count": result["bucket_counts"][bucket.key],
                "share": (
                    ratio(Decimal(result["bucket_counts"][bucket.key]) / Decimal(total))
                    if total
                    else None
                ),
            }
            for bucket in DAYS_BETWEEN_PURCHASES_BUCKETS
        ],
    }


def build_customers(connection, meta: dict, periods) -> dict:
    has_customer_id = _has_customer_id(meta)
    dataset_meta = meta["customer_coverage"]
    dataset_coverage = CustomerCoverage(
        int(dataset_meta["identified_orders"]),
        int(dataset_meta["unidentified_orders"]),
        int(dataset_meta["total_orders"]),
    )
    range_coverage = read_customer_coverage(connection, periods.current.start, periods.current.end)
    body = {
        "module": "customers",
        "range": {
            "start": periods.current.start.isoformat(),
            "end": periods.current.end.isoformat(),
        },
        "comparison": comparison_body(periods),
        "currency": meta["currency"],
        "availability": _availability_body(has_customer_id, dataset_coverage),
        "coverage": {
            "dataset": _coverage_body(
                customer_coverage_tier(has_customer_id, dataset_coverage),
                dataset_coverage,
            ),
            "range": _coverage_body(
                customer_coverage_tier(has_customer_id, dataset_coverage), range_coverage
            ),
        },
        "sections": {},
    }
    tier = customer_coverage_tier(has_customer_id, dataset_coverage)
    if tier in {"normal", "warning"}:
        body["sections"]["identified_customers"] = _identified_customers_body(connection, periods)
        body["sections"]["new_vs_returning"] = _new_vs_returning_body(connection, periods)
        body["sections"]["repeat_purchase"] = _repeat_purchase_body(connection, periods)
        body["sections"]["days_between_purchases"] = _days_between_purchases_body(
            connection, periods
        )
    return body


def _compute_customers(settings: Settings, dataset: AuthorizedDataset, periods) -> dict:
    connection = open_dataset_readonly(dataset_path(settings, dataset.id))
    try:
        return build_customers(connection, dataset.meta, periods)
    finally:
        connection.close()


@router.get("/datasets/{id}/customers", response_model=CustomersResponse)
def get_customers(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    comparison: str = Query(default="previous_period"),
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
    cache: ResponseCache = Depends(get_response_cache),
):
    first, last = _dates(dataset.meta)
    periods = resolve_periods(start, end, comparison, first, last)
    return cached_json(
        cache,
        cache_key(dataset.id, "customers", periods),
        now,
        dataset_expiry(dataset.meta),
        lambda: _compute_customers(settings, dataset, periods),
    )
