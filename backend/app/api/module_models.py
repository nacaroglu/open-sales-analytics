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


class CustomerAvailabilityResponse(BaseModel):
    tier: Literal["missing", "suppressed", "warning", "normal"]
    state: AvailabilityState
    reason: str | None
    warning: AvailabilityResponse | None = None


class CustomerCoverageResponse(BaseModel):
    tier: Literal["missing", "suppressed", "warning", "normal"]
    coverage: float | None
    identified_orders: int
    unidentified_orders: int
    total_orders: int


class CustomerCoverageEnvelope(BaseModel):
    dataset: CustomerCoverageResponse
    range: CustomerCoverageResponse


class ComparedCount(BaseModel):
    value: int
    comparison_value: int | None
    absolute_change: int | None
    percent_change: str | None
    change_status: str | None


class IdentifiedCustomersSection(BaseModel):
    availability: AvailabilityResponse
    value: ComparedCount


class CustomersResponse(BaseModel):
    module: Literal["customers"]
    range: ModuleRange
    comparison: ComparisonResponse
    currency: str
    availability: CustomerAvailabilityResponse
    coverage: CustomerCoverageEnvelope
    sections: dict[str, IdentifiedCustomersSection]


class ComparedMoney(BaseModel):
    value: str = Field(description="Current gross-sales or money value in the active range.")
    comparison_value: str | None = Field(
        description="The corresponding value in the selected comparison period."
    )
    absolute_change: str | None = Field(description="Current value minus comparison value.")
    percent_change: str | None = Field(
        description="API-rounded percentage change, or null for a non-comparable baseline."
    )
    change_status: str | None = Field(
        description="Comparison status such as comparable, no_prior_value, or no_change."
    )


class ComparedCount(BaseModel):
    value: int = Field(description="Current count in the active range.")
    comparison_value: int | None = Field(
        description="The corresponding count in the selected comparison period."
    )
    absolute_change: int | None = Field(description="Current count minus comparison count.")
    percent_change: str | None = Field(
        description="API-rounded percentage change, or null for a non-comparable baseline."
    )
    change_status: str | None = Field(
        description="Comparison status such as comparable, no_prior_value, or no_change."
    )


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
    gross_sales_share: str | None = Field(
        description="Product gross sales divided by total gross sales, as a six-decimal fraction."
    )
    cumulative_share: str | None = Field(
        description="Running gross-sales share in ranking order, as a six-decimal fraction."
    )


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
    weighted_unit_price: str | None = Field(
        description="Quantity-weighted realized unit price for this trend bucket."
    )
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
    order_penetration: str | None = Field(
        description="Distinct orders containing the product divided by all distinct orders, as a fraction."
    )


class ProductPenetrationResponse(BaseModel):
    all_orders: int
    availability: AvailabilityResponse
    products: list[PenetrationProduct]


class ProductDetailPenetration(BaseModel):
    orders_containing_product: int
    all_orders: int
    order_penetration: str | None
    availability: AvailabilityResponse


class BasketProduct(BaseModel):
    product_id: str
    product_name: str


class BasketPair(BaseModel):
    product_a: BasketProduct
    product_b: BasketProduct
    shared_orders: int
    support: str = Field(description="Shared orders divided by eligible basket orders.")
    confidence_a_to_b: str = Field(
        description="Shared orders divided by orders containing product A."
    )
    confidence_b_to_a: str = Field(
        description="Shared orders divided by orders containing product B."
    )
    lift: str = Field(
        description="Directional confidence divided by destination-product order penetration."
    )


class ProductBasketResponse(BaseModel):
    basket_orders: int
    excluded_oversize_orders: int
    max_distinct_products_per_order: int
    min_shared_orders: int
    min_support: str
    eligible_pair_count: int
    availability: AvailabilityResponse
    pairs: list[BasketPair]


class RelatedProduct(BaseModel):
    product: BasketProduct
    shared_orders: int
    support: str
    confidence_from_x: str
    confidence_to_x: str
    lift: str


class RelatedProductsResponse(BaseModel):
    excluded_oversize_orders: int
    availability: AvailabilityResponse
    related_products: list[RelatedProduct]


class ProductsResponse(ModuleEnvelope):
    product_count: int
    availability: AvailabilityResponse
    rankings: ProductRankingsResponse
    share: ProductShareResponse
    growth: ProductGrowthResponse
    dormant: ProductDormancyResponse
    penetration: ProductPenetrationResponse
    basket: ProductBasketResponse


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
    related_products: RelatedProductsResponse
    availability: AvailabilityResponse
