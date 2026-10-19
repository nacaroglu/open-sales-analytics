from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query

from app.analytics.customers.buckets import (
    DAYS_BETWEEN_PURCHASES_BUCKETS,
    PURCHASE_FREQUENCY_BUCKETS,
    RFM_RECENCY_BUCKETS,
)
from app.analytics.customers.cohort_retention import read_cohort_retention
from app.analytics.customers.coverage import read_customer_coverage
from app.analytics.customers.days_between_purchases import read_days_between_purchases
from app.analytics.customers.historical_value import read_historical_customer_value
from app.analytics.customers.identified import read_identified_customer_count
from app.analytics.customers.new_vs_returning import read_new_vs_returning
from app.analytics.customers.purchase_frequency import read_purchase_frequency
from app.analytics.customers.repeat_purchase import read_repeat_purchase
from app.analytics.customers.rfm import read_rfm, read_rfm_drilldown
from app.analytics.shared.availability import (
    Availability,
    AvailabilityState,
    CustomerCoverage,
    customer_availability,
    customer_coverage_tier,
    rounded_coverage,
)
from app.analytics.shared.metrics import RFM_MIN_CUSTOMERS, RFM_NOTE, RFM_SEGMENTS
from app.analytics.shared.periods import recency_anchor
from app.api.module_common import (
    cache_key,
    cached_json,
    compared,
    compared_ratio,
    comparison_body,
    dataset_expiry,
    money,
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


def _cohort_retention_body(connection, periods) -> dict:
    """Current-range only: the start selects cohort rows, the range end is the cutoff."""
    cutoff = recency_anchor(periods.current)
    rows = read_cohort_retention(connection, periods.current.start, cutoff)
    availability = (
        Availability(AvailabilityState.AVAILABLE)
        if rows
        else Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            "No identified customer was acquired in a month that overlaps the selected range, "
            "so there is no acquisition cohort.",
        )
    )
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "data_cutoff": cutoff.isoformat(),
        "rows": [
            {
                "cohort_month": row["cohort_month"].strftime("%Y-%m"),
                "cohort_size": row["cohort_size"],
                "complete_months": sum(cell["state"] == "complete" for cell in row["cells"]),
                "cells": [
                    {
                        "month_offset": cell["month_offset"],
                        "state": cell["state"],
                        "retained_count": cell["retained_count"],
                        "retention": (
                            None
                            if cell["retained_count"] is None
                            else ratio(
                                Decimal(cell["retained_count"]) / Decimal(row["cohort_size"])
                            )
                        ),
                    }
                    for cell in row["cells"]
                ],
            }
            for row in rows
        ],
    }


_MONEY_STEP = Decimal("0.0001")


def _rounded_money(value: Decimal | None) -> str | None:
    """Money rounded half-up to 4 decimals; ``money()`` alone only formats."""
    return None if value is None else money(value.quantize(_MONEY_STEP, rounding=ROUND_HALF_UP))


def _historical_customer_value_body(connection, periods) -> dict:
    """Current-range only: the cohort_retention members, valued up to the range end."""
    cutoff = recency_anchor(periods.current)
    result = read_historical_customer_value(connection, periods.current.start, cutoff)
    count = result["customer_count"]
    total = result["total_value"]
    if not count:
        availability = Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            "No identified customer was acquired in a month that overlaps the selected range, "
            "so there is no customer whose value can be observed.",
        )
    elif not total:
        availability = Availability(
            AvailabilityState.ZERO_RESULT,
            "The identified customers acquired in the selected months have no gross sales "
            "up to the end of the range.",
        )
    else:
        availability = Availability(AvailabilityState.AVAILABLE)
    rows = result["rows"]
    width = len(rows[0]["cells"]) if rows else 0
    all_cohorts = []
    for offset in range(width):
        complete = [
            (row["cells"][offset]["cumulative_gross_sales"], row["cohort_size"])
            for row in rows
            if row["cells"][offset]["state"] == "complete"
        ]
        sales = sum((value for value, _ in complete if value is not None), Decimal(0))
        size = sum(size for _, size in complete)
        all_cohorts.append(
            {
                "month_offset": offset,
                "value_per_customer": _rounded_money(sales / size) if size else None,
                "contributing_cohorts": len(complete),
            }
        )
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "data_cutoff": cutoff.isoformat(),
        "customer_count": count,
        "average": _rounded_money(total / count) if count else None,
        "median": _rounded_money(result["median"]),
        "rows": [
            {
                "cohort_month": row["cohort_month"].strftime("%Y-%m"),
                "cohort_size": row["cohort_size"],
                "cells": [
                    {
                        "month_offset": cell["month_offset"],
                        "state": cell["state"],
                        "value_per_customer": (
                            None
                            if cell["cumulative_gross_sales"] is None
                            else _rounded_money(cell["cumulative_gross_sales"] / row["cohort_size"])
                        ),
                    }
                    for cell in row["cells"]
                ],
            }
            for row in rows
        ],
        "all_cohorts": all_cohorts,
    }


def _rfm_body(connection, periods) -> dict:
    """Current-range only: all identified activity through the range end, no comparison."""
    anchor = recency_anchor(periods.current)
    result = read_rfm(connection, anchor)
    count = result["customer_count"]
    if count < RFM_MIN_CUSTOMERS:
        availability = Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            f"RFM needs at least {RFM_MIN_CUSTOMERS} identified customers.",
        )
        segments = []
    else:
        availability = Availability(AvailabilityState.AVAILABLE)
        segments = [
            {
                "segment": segment.name,
                "customer_count": result["segment_counts"][segment.name],
                "share": ratio(Decimal(result["segment_counts"][segment.name]) / Decimal(count)),
            }
            for segment in RFM_SEGMENTS
        ]
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "customer_count": count,
        "recency_anchor": anchor.isoformat(),
        "note": RFM_NOTE,
        "segments": segments,
    }


def _rfm_drilldown_body(connection, periods) -> dict:
    """Current-range only: per-segment aggregates of the same population as ``rfm``."""
    anchor = recency_anchor(periods.current)
    result = read_rfm_drilldown(connection, anchor)
    count = result["customer_count"]
    total = result["gross_sales"]
    segments = []
    if count < RFM_MIN_CUSTOMERS:
        availability = Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            f"RFM needs at least {RFM_MIN_CUSTOMERS} identified customers.",
        )
    else:
        availability = Availability(AvailabilityState.AVAILABLE)
        segments = [
            {
                "segment": segment["segment"],
                "customer_count": segment["customer_count"],
                "gross_sales": _rounded_money(segment["gross_sales"]),
                "gross_sales_share": ratio(segment["gross_sales"] / total) if total else None,
                "recency_distribution": [
                    {
                        "key": bucket.key,
                        "min_days": bucket.min_days,
                        "max_days": bucket.max_days,
                        "customer_count": segment["recency_counts"][bucket.key],
                    }
                    for bucket in RFM_RECENCY_BUCKETS
                ],
                "frequency_distribution": [
                    {
                        "key": bucket.key,
                        "min_orders": bucket.min_orders,
                        "max_orders": bucket.max_orders,
                        "customer_count": segment["frequency_counts"][bucket.key],
                    }
                    for bucket in PURCHASE_FREQUENCY_BUCKETS
                ],
            }
            for segment in result["segments"]
        ]
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "customer_count": count,
        "recency_anchor": anchor.isoformat(),
        "gross_sales": _rounded_money(total),
        "segments": segments,
    }


def _purchase_frequency_body(connection, periods) -> dict:
    """Current-range only: identified customers grouped by orders through range end."""
    result = read_purchase_frequency(connection, periods.current.end)
    count = result["customer_count"]
    availability = (
        Availability(AvailabilityState.AVAILABLE)
        if count
        else Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            "No identified customers placed an order on or before the selected end date.",
        )
    )
    return {
        "availability": {
            "state": availability.state,
            "reason": availability.reason,
        },
        "customer_count": count,
        "single_order_share": (
            ratio(Decimal(result["bucket_counts"]["1"]) / Decimal(count)) if count else None
        ),
        "buckets": [
            {
                "key": bucket.key,
                "min_orders": bucket.min_orders,
                "max_orders": bucket.max_orders,
                "customer_count": result["bucket_counts"][bucket.key],
                "share": (
                    ratio(Decimal(result["bucket_counts"][bucket.key]) / Decimal(count))
                    if count
                    else None
                ),
            }
            for bucket in PURCHASE_FREQUENCY_BUCKETS
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
        body["sections"]["cohort_retention"] = _cohort_retention_body(connection, periods)
        body["sections"]["historical_customer_value"] = _historical_customer_value_body(
            connection, periods
        )
        body["sections"]["rfm"] = _rfm_body(connection, periods)
        body["sections"]["rfm_drilldown"] = _rfm_drilldown_body(connection, periods)
        body["sections"]["purchase_frequency"] = _purchase_frequency_body(connection, periods)
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
