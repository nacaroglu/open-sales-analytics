from typing import Literal

from pydantic import BaseModel

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


class ProductsResponse(ModuleEnvelope):
    product_count: int
    availability: AvailabilityResponse


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
    availability: AvailabilityResponse
