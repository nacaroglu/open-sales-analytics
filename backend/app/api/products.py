from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.analytics.products.top_products import (
    read_product_count,
    read_product_identity,
    read_product_kpis,
    read_product_trend,
)
from app.analytics.shared.availability import AvailabilityState
from app.analytics.shared.buckets import choose_granularity
from app.api.module_common import compared, envelope, resolve_periods
from app.api.module_models import ProductDetailResponse, ProductsResponse
from app.auth import AuthorizedDataset, require_dataset
from app.config import Settings, get_settings
from app.errors import ApiError
from app.importer import dataset_path
from app.schema import open_dataset_readonly

router = APIRouter(prefix="/api")


def _dates(meta: dict) -> tuple[date, date]:
    return date.fromisoformat(meta["date_range"]["min"]), date.fromisoformat(
        meta["date_range"]["max"]
    )


def _availability(has_sales: bool) -> dict:
    if has_sales:
        return {"state": AvailabilityState.AVAILABLE, "reason": None}
    return {
        "state": AvailabilityState.ZERO_RESULT,
        "reason": "No products have sales in the selected range.",
    }


def _trend_body(rows: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "bucket_start": row["bucket_start"].isoformat(),
            "gross_sales": f"{row['gross_sales']:.4f}",
        }
        for row in rows
    ]


@router.get("/datasets/{id}/products", response_model=ProductsResponse)
def get_products(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    comparison: str = Query(default="previous_period"),
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
):
    first, last = _dates(dataset.meta)
    periods = resolve_periods(start, end, comparison, first, last)
    connection = open_dataset_readonly(dataset_path(settings, dataset.id))
    try:
        product_count = read_product_count(connection, periods.current.start, periods.current.end)
    finally:
        connection.close()
    body = envelope(
        dataset.meta,
        periods,
        choose_granularity(periods.current.start, periods.current.end),
    )
    body["product_count"] = product_count
    body["availability"] = _availability(product_count > 0)
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/datasets/{id}/products/detail", response_model=ProductDetailResponse)
def get_product_detail(
    product_id: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    comparison: str = Query(default="previous_period"),
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
):
    if not product_id:
        raise ApiError(400, "invalid_request", "product_id is required.")
    first, last = _dates(dataset.meta)
    periods = resolve_periods(start, end, comparison, first, last)
    granularity = choose_granularity(periods.current.start, periods.current.end)
    connection = open_dataset_readonly(dataset_path(settings, dataset.id))
    try:
        product = read_product_identity(connection, product_id)
        if product is None:
            raise ApiError(404, "product_not_found", "The product was not found in this dataset.")
        current = read_product_kpis(
            connection, product_id, periods.current.start, periods.current.end
        )
        baseline = (
            read_product_kpis(
                connection,
                product_id,
                periods.comparison.comparison_start,
                periods.comparison.comparison_end,
            )
            if periods.comparison.available
            else None
        )
        body = envelope(dataset.meta, periods, granularity)
        body["product"] = product
        body["kpis"] = {
            "gross_sales": compared(
                current["gross_sales"], None if baseline is None else baseline["gross_sales"], True
            ),
            "units_sold": compared(
                current["units_sold"], None if baseline is None else baseline["units_sold"], False
            ),
            "orders": compared(
                current["orders"], None if baseline is None else baseline["orders"], False
            ),
        }
        body["trend"] = _trend_body(
            read_product_trend(
                connection, product_id, periods.current.start, periods.current.end, granularity
            )
        )
        body["availability"] = _availability(current["orders"] > 0)
    finally:
        connection.close()
    return JSONResponse(body, headers={"Cache-Control": "no-store"})
