from typing import Literal

from pydantic import BaseModel, Field

from app.analytics.shared.availability import AvailabilityState


class AvailabilityResponse(BaseModel):
    state: AvailabilityState
    reason: str | None


class ComparisonDates(BaseModel):
    start: str
    end: str


class ComparisonResponse(BaseModel):
    mode: Literal["previous_period", "previous_year"]
    current: ComparisonDates
    comparison: ComparisonDates
    state: AvailabilityState
    reason: str | None


class ModuleRange(BaseModel):
    start: str
    end: str


class ComparedMoney(BaseModel):
    value: str
    comparison_value: str | None
    absolute_change: str | None
    percent_change: str | None
    change_status: str | None


class ComparedCount(BaseModel):
    value: int
    comparison_value: int | None
    absolute_change: int | None
    percent_change: str | None
    change_status: str | None


class ModuleEnvelope(BaseModel):
    range: ModuleRange
    currency: str
    granularity: str
    comparison: ComparisonResponse


class RankingProduct(BaseModel):
    product_id: str
    product_name: str
    gross_sales: str
    units_sold: int
    distinct_orders: int


class ProductRankingsResponse(BaseModel):
    availability: AvailabilityResponse
    by_gross_sales: list[RankingProduct]
    by_units_sold: list[RankingProduct]
    by_orders: list[RankingProduct]


class ShareProduct(BaseModel):
    product_id: str
    product_name: str
    gross_sales: str
    gross_sales_share: str | None
    cumulative_share: str | None


class ProductShareResponse(BaseModel):
    products: list[ShareProduct]
    product_count: int
    total_gross_sales: str
    top_20_percent_product_count: int | None
    top_20_percent_share: str | None
    products_to_80_percent: int | None
    availability: AvailabilityResponse


class GrowthProduct(BaseModel):
    product_id: str
    product_name: str
    gross_sales: ComparedMoney
    units_sold: ComparedCount
    orders: ComparedCount
    classification: Literal["new", "no_current_sales", "rising", "falling", "unchanged"] | None


class ProductGrowthResponse(BaseModel):
    availability: AvailabilityResponse
    products: list[GrowthProduct]
    rising: list[GrowthProduct]
    falling: list[GrowthProduct]


class DormantProduct(BaseModel):
    product_id: str
    product_name: str
    last_sale_date: str
    days_inactive: int
    earlier_gross_sales: str
    earlier_orders: int


class ProductDormancyResponse(BaseModel):
    window_days: int
    anchor_date: str
    availability: AvailabilityResponse
    products: list[DormantProduct]


class PriceHistoryBucket(BaseModel):
    bucket_start: str
    weighted_unit_price: str | None
    units_sold: int


class ProductPriceHistoryResponse(BaseModel):
    granularity: str
    availability: AvailabilityResponse
    buckets: list[PriceHistoryBucket]


class PenetrationProduct(BaseModel):
    product_id: str
    product_name: str
    orders_containing_product: int
    all_orders: int
    order_penetration: str | None


class ProductPenetrationResponse(BaseModel):
    all_orders: int
    availability: AvailabilityResponse
    products: list[PenetrationProduct]


class ProductDetailPenetration(BaseModel):
    orders_containing_product: int
    all_orders: int
    order_penetration: str | None
    availability: AvailabilityResponse


class ProductsResponse(ModuleEnvelope):
    product_count: int
    availability: AvailabilityResponse
    rankings: ProductRankingsResponse
    share: ProductShareResponse
    growth: ProductGrowthResponse
    dormant: ProductDormancyResponse
    penetration: ProductPenetrationResponse


class OverviewKpis(BaseModel):
    gross_sales: ComparedMoney
    orders: ComparedCount
    units_sold: ComparedCount
    average_order_value: ComparedMoney


class OverviewResponse(ModuleEnvelope):
    kpis: OverviewKpis
    trend: list[dict[str, str]]
    comparison_trend: list[dict[str, str]] | None
    top_products: list[dict[str, str | int]]


class ProductResponse(BaseModel):
    product_id: str
    product_name: str


class ProductKpis(BaseModel):
    gross_sales: ComparedMoney
    units_sold: ComparedCount
    orders: ComparedCount


class ProductDetailResponse(ModuleEnvelope):
    product: ProductResponse
    kpis: ProductKpis
    trend: list[dict[str, str]]
    price_history: ProductPriceHistoryResponse = Field(
        description="Quantity-weighted realized average unit price by sales-trend bucket."
    )
    penetration: ProductDetailPenetration
    availability: AvailabilityResponse
