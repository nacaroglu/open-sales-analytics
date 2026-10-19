from datetime import date, datetime

from fastapi import APIRouter, Depends, Query

from app.analytics.customers.coverage import read_customer_coverage
from app.analytics.shared.availability import (
    CustomerCoverage,
    customer_availability,
    customer_coverage_tier,
    rounded_coverage,
)
from app.api.module_common import (
    cache_key,
    cached_json,
    comparison_body,
    dataset_expiry,
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


def build_customers(connection, meta: dict, periods) -> dict:
    has_customer_id = _has_customer_id(meta)
    dataset_meta = meta["customer_coverage"]
    dataset_coverage = CustomerCoverage(
        int(dataset_meta["identified_orders"]),
        int(dataset_meta["unidentified_orders"]),
        int(dataset_meta["total_orders"]),
    )
    range_coverage = read_customer_coverage(connection, periods.current.start, periods.current.end)
    return {
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
