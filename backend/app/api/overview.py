from datetime import date, datetime

from fastapi import APIRouter, Depends, Query

from app.analytics.overview.kpis import read_kpis
from app.analytics.overview.trend import read_trend
from app.analytics.products.top_products import read_top_products
from app.analytics.shared.buckets import choose_granularity
from app.api.module_common import (
    cache_key,
    cached_json,
    compared,
    dataset_expiry,
    envelope,
    resolve_periods,
)
from app.api.module_models import OverviewResponse
from app.auth import AuthorizedDataset, get_now, require_dataset
from app.config import Settings, get_settings
from app.domain_telemetry import instrument_operation
from app.importer import dataset_path
from app.response_cache import ResponseCache, get_response_cache
from app.schema import open_dataset_readonly

router = APIRouter(prefix="/api")


def _dates(meta: dict) -> tuple[date, date]:
    return date.fromisoformat(meta["date_range"]["min"]), date.fromisoformat(
        meta["date_range"]["max"]
    )


def _trend_body(trend: dict) -> list[dict[str, str]]:
    return [
        {
            "bucket_start": bucket["bucket_start"].isoformat(),
            "gross_sales": f"{bucket['gross_sales']:.4f}",
        }
        for bucket in trend["buckets"]
    ]


def _top_body(rows: list[dict]) -> list[dict]:
    return [
        {
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "gross_sales": f"{row['gross_sales']:.4f}",
            "units_sold": row["units_sold"],
            "distinct_orders": row["distinct_orders"],
        }
        for row in rows
    ]


@instrument_operation("osa.analytics.overview.query", module="overview")
def build_overview(connection, meta: dict, periods) -> dict:
    granularity = choose_granularity(periods.current.start, periods.current.end)
    current = read_kpis(connection, periods.current.start, periods.current.end)
    baseline = (
        read_kpis(
            connection,
            periods.comparison.comparison_start,
            periods.comparison.comparison_end,
        )
        if periods.comparison.available
        else None
    )
    body = envelope(meta, periods, granularity)
    body["kpis"] = {
        "gross_sales": compared(
            current["gross_sales"], None if baseline is None else baseline["gross_sales"], True
        ),
        "orders": compared(
            current["orders"], None if baseline is None else baseline["orders"], False
        ),
        "units_sold": compared(
            current["units_sold"], None if baseline is None else baseline["units_sold"], False
        ),
        "average_order_value": compared(
            current["average_order_value"],
            None if baseline is None else baseline["average_order_value"],
            True,
        ),
    }
    current_trend = read_trend(connection, periods.current.start, periods.current.end, granularity)
    body["trend"] = _trend_body(current_trend)
    body["comparison_trend"] = (
        _trend_body(
            read_trend(
                connection,
                periods.comparison.comparison_start,
                periods.comparison.comparison_end,
                granularity,
            )
        )
        if periods.comparison.available
        else None
    )
    body["top_products"] = _top_body(
        read_top_products(connection, periods.current.start, periods.current.end)
    )
    return body


def _compute_overview(settings: Settings, dataset: AuthorizedDataset, periods) -> dict:
    connection = open_dataset_readonly(dataset_path(settings, dataset.id))
    try:
        return build_overview(connection, dataset.meta, periods)
    finally:
        connection.close()


@router.get("/datasets/{id}/overview", response_model=OverviewResponse)
def get_overview(
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
        cache_key(dataset.id, "overview", periods),
        now,
        dataset_expiry(dataset.meta),
        lambda: _compute_overview(settings, dataset, periods),
    )
