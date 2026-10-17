from datetime import date, datetime

from fastapi import APIRouter, Depends, Query

from app.analytics.products.basket import read_product_basket
from app.analytics.products.dormancy import read_dormant_products
from app.analytics.products.growth import read_product_growth
from app.analytics.products.penetration import read_product_penetration
from app.analytics.products.price_history import read_product_price_history
from app.analytics.products.share import read_product_share
from app.analytics.products.top_products import (
    read_product_count,
    read_product_identity,
    read_product_kpis,
    read_product_rankings,
    read_product_trend,
)
from app.analytics.shared.availability import AvailabilityState
from app.analytics.shared.buckets import choose_granularity
from app.analytics.shared.metrics import (
    BASKET_MIN_SHARED_ORDERS,
    BASKET_MIN_SUPPORT,
    DORMANCY_WINDOWS,
)
from app.api.module_common import (
    cache_key,
    cached_json,
    compared,
    dataset_expiry,
    envelope,
    resolve_periods,
)
from app.api.module_models import ProductDetailResponse, ProductsResponse
from app.auth import AuthorizedDataset, get_now, require_dataset
from app.config import Settings, get_settings
from app.errors import ApiError
from app.importer import dataset_path
from app.response_cache import ResponseCache, get_response_cache
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


def _ranking_body(rankings: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {
        name: [{**row, "gross_sales": f"{row['gross_sales']:.4f}"} for row in rows]
        for name, rows in rankings.items()
    }


def _share_body(share: dict) -> dict:
    def fraction(value):
        return None if value is None else f"{value:.6f}"

    return {
        "products": [
            {
                **row,
                "gross_sales": f"{row['gross_sales']:.4f}",
                "gross_sales_share": fraction(row["gross_sales_share"]),
                "cumulative_share": fraction(row["cumulative_share"]),
            }
            for row in share["products"]
        ],
        "product_count": share["product_count"],
        "total_gross_sales": f"{share['total_gross_sales']:.4f}",
        "top_20_percent_product_count": share["top_20_percent_product_count"],
        "top_20_percent_share": fraction(share["top_20_percent_share"]),
        "products_to_80_percent": share["products_to_80_percent"],
        "availability": {
            "state": share["availability"].state,
            "reason": share["availability"].reason,
        },
    }


def _growth_body(growth: dict) -> dict:
    def compared_body(metric: dict, money: bool) -> dict:
        def number(value):
            if value is None:
                return None
            return f"{value:.4f}" if money else int(value)

        return {
            "value": number(metric["value"]),
            "comparison_value": number(metric["comparison_value"]),
            "absolute_change": number(metric["absolute_change"]),
            "percent_change": (
                None if metric["percent_change"] is None else f"{metric['percent_change']:.2f}"
            ),
            "change_status": metric["change_status"],
        }

    def product_body(product: dict) -> dict:
        return {
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "gross_sales": compared_body(product["gross_sales"], True),
            "units_sold": compared_body(product["units_sold"], False),
            "orders": compared_body(product["orders"], False),
            "classification": product["classification"],
        }

    return {
        "availability": {
            "state": growth["availability"].state,
            "reason": growth["availability"].reason,
        },
        "products": [product_body(product) for product in growth["products"]],
        "rising": [product_body(product) for product in growth["rising"]],
        "falling": [product_body(product) for product in growth["falling"]],
    }


def _dormancy_body(dormancy: dict) -> dict:
    return {
        "window_days": dormancy["window_days"],
        "anchor_date": dormancy["anchor_date"].isoformat(),
        "availability": {
            "state": dormancy["availability"].state,
            "reason": dormancy["availability"].reason,
        },
        "products": [
            {
                **product,
                "last_sale_date": product["last_sale_date"].isoformat(),
                "earlier_gross_sales": f"{product['earlier_gross_sales']:.4f}",
            }
            for product in dormancy["products"]
        ],
    }


def _dormancy_window(value: str) -> int:
    if value not in {str(window) for window in DORMANCY_WINDOWS}:
        raise ApiError(400, "invalid_request", "dormancy_days must be 30, 60 or 90.")
    return int(value)


def _price_history_body(history: dict) -> dict:
    return {
        "granularity": history["granularity"],
        "availability": {
            "state": history["availability"].state,
            "reason": history["availability"].reason,
        },
        "buckets": [
            {
                "bucket_start": bucket["bucket_start"].isoformat(),
                "weighted_unit_price": (
                    None
                    if bucket["weighted_unit_price"] is None
                    else f"{bucket['weighted_unit_price']:.4f}"
                ),
                "units_sold": bucket["units_sold"],
            }
            for bucket in history["buckets"]
        ],
    }


def _penetration_body(penetration: dict) -> dict:
    return {
        "all_orders": penetration["all_orders"],
        "availability": {
            "state": penetration["availability"].state,
            "reason": penetration["availability"].reason,
        },
        "products": [
            {
                **product,
                "order_penetration": (
                    None
                    if product["order_penetration"] is None
                    else f"{product['order_penetration']:.6f}"
                ),
            }
            for product in penetration["products"]
        ],
    }


def _detail_penetration_body(penetration: dict) -> dict:
    product = penetration["products"][0]
    return {
        "orders_containing_product": product["orders_containing_product"],
        "all_orders": product["all_orders"],
        "order_penetration": (
            None if product["order_penetration"] is None else f"{product['order_penetration']:.6f}"
        ),
        "availability": {
            "state": penetration["availability"].state,
            "reason": penetration["availability"].reason,
        },
    }


def _fraction(value) -> str:
    return f"{value:.6f}"


def _basket_body(basket: dict) -> dict:
    return {
        "basket_orders": basket["basket_orders"],
        "min_shared_orders": BASKET_MIN_SHARED_ORDERS,
        "min_support": _fraction(BASKET_MIN_SUPPORT),
        "eligible_pair_count": basket["eligible_pair_count"],
        "availability": {
            "state": basket["availability"].state,
            "reason": basket["availability"].reason,
        },
        "pairs": [
            {
                **pair,
                "support": _fraction(pair["support"]),
                "confidence_a_to_b": _fraction(pair["confidence_a_to_b"]),
                "confidence_b_to_a": _fraction(pair["confidence_b_to_a"]),
                "lift": _fraction(pair["lift"]),
            }
            for pair in basket["pairs"]
        ],
    }


def _related_products_body(basket: dict) -> dict:
    return {
        "availability": {
            "state": basket["related_availability"].state,
            "reason": basket["related_availability"].reason,
        },
        "related_products": [
            {
                **related,
                "support": _fraction(related["support"]),
                "confidence_from_x": _fraction(related["confidence_from_x"]),
                "confidence_to_x": _fraction(related["confidence_to_x"]),
                "lift": _fraction(related["lift"]),
            }
            for related in basket["related_products"]
        ],
    }


@router.get("/datasets/{id}/products", response_model=ProductsResponse)
def get_products(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    comparison: str = Query(default="previous_period"),
    dormancy_days: str = Query(default="60"),
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
    cache: ResponseCache = Depends(get_response_cache),
):
    window_days = _dormancy_window(dormancy_days)
    first, last = _dates(dataset.meta)
    periods = resolve_periods(start, end, comparison, first, last)

    def compute() -> dict:
        connection = open_dataset_readonly(dataset_path(settings, dataset.id))
        try:
            product_count = read_product_count(
                connection, periods.current.start, periods.current.end
            )
            rankings = read_product_rankings(connection, periods.current.start, periods.current.end)
            share = read_product_share(connection, periods.current.start, periods.current.end)
            growth = read_product_growth(connection, periods.current, periods.comparison)
            dormancy = read_dormant_products(connection, periods.current, window_days)
            penetration = read_product_penetration(
                connection, periods.current.start, periods.current.end
            )
            basket = read_product_basket(connection, periods.current.start, periods.current.end)
        finally:
            connection.close()
        body = envelope(
            dataset.meta,
            periods,
            choose_granularity(periods.current.start, periods.current.end),
        )
        body["product_count"] = product_count
        body["availability"] = _availability(product_count > 0)
        body["rankings"] = {
            "availability": _availability(product_count > 0),
            **_ranking_body(rankings),
        }
        body["share"] = _share_body(share)
        body["growth"] = _growth_body(growth)
        body["dormant"] = _dormancy_body(dormancy)
        body["penetration"] = _penetration_body(penetration)
        body["basket"] = _basket_body(basket)
        return body

    return cached_json(
        cache,
        cache_key(dataset.id, "products", periods, (("dormancy_days", str(window_days)),)),
        now,
        dataset_expiry(dataset.meta),
        compute,
    )


@router.get("/datasets/{id}/products/detail", response_model=ProductDetailResponse)
def get_product_detail(
    product_id: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    comparison: str = Query(default="previous_period"),
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
    cache: ResponseCache = Depends(get_response_cache),
):
    if not product_id:
        raise ApiError(400, "invalid_request", "product_id is required.")
    first, last = _dates(dataset.meta)
    periods = resolve_periods(start, end, comparison, first, last)
    granularity = choose_granularity(periods.current.start, periods.current.end)

    def compute() -> dict:
        connection = open_dataset_readonly(dataset_path(settings, dataset.id))
        try:
            product = read_product_identity(connection, product_id)
            if product is None:
                raise ApiError(
                    404, "product_not_found", "The product was not found in this dataset."
                )
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
                    current["gross_sales"],
                    None if baseline is None else baseline["gross_sales"],
                    True,
                ),
                "units_sold": compared(
                    current["units_sold"],
                    None if baseline is None else baseline["units_sold"],
                    False,
                ),
                "orders": compared(
                    current["orders"],
                    None if baseline is None else baseline["orders"],
                    False,
                ),
            }
            body["trend"] = _trend_body(
                read_product_trend(
                    connection,
                    product_id,
                    periods.current.start,
                    periods.current.end,
                    granularity,
                )
            )
            body["price_history"] = _price_history_body(
                read_product_price_history(
                    connection,
                    product_id,
                    periods.current.start,
                    periods.current.end,
                    granularity,
                )
            )
            body["penetration"] = _detail_penetration_body(
                read_product_penetration(
                    connection,
                    periods.current.start,
                    periods.current.end,
                    product_id=product_id,
                )
            )
            body["related_products"] = _related_products_body(
                read_product_basket(
                    connection,
                    periods.current.start,
                    periods.current.end,
                    product_id=product_id,
                )
            )
            body["availability"] = _availability(current["orders"] > 0)
            return body
        finally:
            connection.close()

    return cached_json(
        cache,
        cache_key(dataset.id, "product_detail", periods, (("product_id", product_id),)),
        now,
        dataset_expiry(dataset.meta),
        compute,
    )
