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


class IdentifiedCustomersSection(BaseModel):
    availability: AvailabilityResponse
    value: ComparedCount


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


class NewVsReturningSection(BaseModel):
    availability: AvailabilityResponse
    new_customer_gross_sales: ComparedMoney = Field(
        description="Identified gross sales on each customer's full-history first purchase date."
    )
    returning_customer_gross_sales: ComparedMoney = Field(
        description="Identified gross sales dated after each customer's first purchase date."
    )
    identified_gross_sales: ComparedMoney = Field(
        description="New plus returning customer gross sales; unidentified rows are excluded."
    )


class ComparedRatio(BaseModel):
    value: float | None = Field(
        description="Current ratio between 0 and 1, rounded half-up to 4 decimals; null when undefined."
    )
    comparison_value: float | None = Field(
        description="Comparison-period ratio, or null when unavailable or undefined."
    )
    absolute_change: float | None = Field(
        description="Current ratio minus comparison ratio, rounded half-up to 4 decimals."
    )
    percent_change: str | None = Field(
        description="Percentage change from the exact ratios with 2 decimals, or null."
    )
    change_status: str | None = Field(
        description="Shared comparison status, or null when the change is undefined."
    )


class RepeatPurchaseSection(BaseModel):
    availability: AvailabilityResponse
    active_customers: ComparedCount = Field(
        description="Identified customers with an order in the active range."
    )
    repeat_customers: ComparedCount = Field(
        description="Active customers with two or more orders through the range end."
    )
    repeat_purchase_rate: ComparedRatio = Field(
        description="repeat_customers divided by active_customers."
    )


class DaysBetweenPurchasesBucket(BaseModel):
    key: str = Field(description='Bucket key, for example "0", "1-7" or "366+".')
    min_days: int = Field(description="Smallest interval in the bucket, in days (inclusive).")
    max_days: int | None = Field(
        description="Largest interval in the bucket, in days (inclusive); null when open-ended."
    )
    interval_count: int = Field(description="Included intervals in this bucket.")
    share: float | None = Field(
        description="interval_count divided by the section interval_count, rounded half-up "
        "to 4 decimals; null when the section has no interval."
    )


class DaysBetweenPurchasesSection(BaseModel):
    availability: AvailabilityResponse
    median_days: float | None = Field(
        description="Median days between consecutive identified orders whose later order is "
        "in the range; null when there is no included interval."
    )
    interval_count: int = Field(description="Included intervals between consecutive orders.")
    contributing_customers: int = Field(
        description="Identified customers with at least one included interval."
    )
    buckets: list[DaysBetweenPurchasesBucket] = Field(
        description="All nine fixed day buckets, in order, including empty ones."
    )


class CohortRetentionCell(BaseModel):
    month_offset: int = Field(description="Months since the acquisition month (0 = acquisition).")
    state: Literal["complete", "partial", "not_observed"] = Field(
        description="complete: the whole month is on or before data_cutoff; partial: the month "
        "contains data_cutoff but does not end on it (counts so far); not_observed: the month "
        "starts after data_cutoff (counts are null)."
    )
    retained_count: int | None = Field(
        description="Cohort members with an identified line in this month, on or before "
        "data_cutoff; null when not_observed."
    )
    retention: float | None = Field(
        description="retained_count divided by cohort_size, rounded half-up to 4 decimals; "
        "null when not_observed."
    )


class CohortRetentionRow(BaseModel):
    cohort_month: str = Field(description="Acquisition month, YYYY-MM.")
    cohort_size: int = Field(
        description="Identified customers whose full-history first order is in this month "
        "and on or before data_cutoff."
    )
    complete_months: int = Field(description="Number of complete cells in the row.")
    cells: list[CohortRetentionCell] = Field(
        description="Cells ordered by month_offset; every row has the same number of cells."
    )


class CohortRetentionSection(BaseModel):
    availability: AvailabilityResponse
    data_cutoff: str = Field(description="The range end (YYYY-MM-DD); later activity is ignored.")
    rows: list[CohortRetentionRow] = Field(
        description="Acquisition cohorts overlapping the range, oldest first."
    )


class HistoricalCustomerValueCell(BaseModel):
    month_offset: int = Field(description="Months since the acquisition month (0 = acquisition).")
    state: Literal["complete", "partial", "not_observed"] = Field(
        description="The matching cohort_retention cell state: complete (the whole month is on "
        "or before data_cutoff), partial (the month contains data_cutoff; sales so far) or "
        "not_observed (the month starts after data_cutoff; value is null)."
    )
    value_per_customer: str | None = Field(
        description="Observed cumulative identified gross sales of the cohort from its "
        "acquisition month through the end of this month (capped at data_cutoff), divided by "
        "cohort_size; money, 4 decimals rounded half-up; null when not_observed."
    )


class HistoricalCustomerValueRow(BaseModel):
    cohort_month: str = Field(description="Acquisition month, YYYY-MM.")
    cohort_size: int = Field(
        description="Identified customers whose full-history first order is in this month "
        "and on or before data_cutoff."
    )
    cells: list[HistoricalCustomerValueCell] = Field(
        description="Cells ordered by month_offset, the same offsets as cohort_retention."
    )


class HistoricalCustomerValueCurvePoint(BaseModel):
    month_offset: int = Field(description="Months since the acquisition month (0 = acquisition).")
    value_per_customer: str | None = Field(
        description="Summed cumulative gross sales of the cohorts whose cell at this offset is "
        "complete, divided by the sum of their cohort sizes; money, 4 decimals rounded "
        "half-up; null when no cohort is complete at this offset."
    )
    contributing_cohorts: int = Field(
        description="Number of cohorts whose cell at this offset is complete."
    )


class HistoricalCustomerValueSection(BaseModel):
    """Observed Historical Customer Value: gross sales already observed, not a forecast."""

    availability: AvailabilityResponse
    data_cutoff: str = Field(description="The range end (YYYY-MM-DD); later activity is ignored.")
    customer_count: int = Field(
        description="Identified customers in the acquisition cohorts overlapping the range "
        "(the cohort_retention members)."
    )
    average: str | None = Field(
        description="Observed identified gross sales of these customers up to data_cutoff "
        "(including sales before the range start) divided by customer_count; money, 4 "
        "decimals rounded half-up; null when customer_count is 0."
    )
    median: str | None = Field(
        description="Median observed per-customer gross sales up to data_cutoff (mean of the "
        "two middle values for an even count); money, 4 decimals rounded half-up; null when "
        "customer_count is 0."
    )
    rows: list[HistoricalCustomerValueRow] = Field(
        description="Cumulative value per customer by cohort age, one row per cohort_retention "
        "row, oldest first."
    )
    all_cohorts: list[HistoricalCustomerValueCurvePoint] = Field(
        description="All-cohorts curve over complete cells, one point per month_offset."
    )


class CustomerSections(BaseModel):
    """Customer analytics sections; absent sections are omitted from the JSON."""

    identified_customers: IdentifiedCustomersSection | None = None
    new_vs_returning: NewVsReturningSection | None = None
    repeat_purchase: RepeatPurchaseSection | None = None
    days_between_purchases: DaysBetweenPurchasesSection | None = None
    cohort_retention: CohortRetentionSection | None = None
    historical_customer_value: HistoricalCustomerValueSection | None = None


class CustomersResponse(BaseModel):
    module: Literal["customers"]
    range: ModuleRange
    comparison: ComparisonResponse
    currency: str
    availability: CustomerAvailabilityResponse
    coverage: CustomerCoverageEnvelope
    sections: CustomerSections


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
