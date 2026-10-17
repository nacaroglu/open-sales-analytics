"""Authoritative metric definitions shared by APIs, tests, and UI labels."""

from dataclasses import dataclass

_UNITS = frozenset({"money", "count", "ratio", "percent", "days"})
_ACTIVE_RANGE = "The active reporting range, inclusive of its start and end dates."
_BASKET_INSUFFICIENT_DATA = (
    "A pair is eligible only when it occurs in at least 10 shared orders and support is at "
    "least 0.1%. Orders containing more than 100 distinct products are excluded from basket "
    "analysis only."
)


@dataclass(frozen=True)
class MetricDefinition:
    """The stable, documented contract for one analytics metric."""

    key: str
    label: str
    unit: str
    formula: str
    numerator: str
    denominator: str | None
    time_window: str
    insufficient_data: str

    def __post_init__(self) -> None:
        for field_name in (
            "key",
            "label",
            "unit",
            "formula",
            "numerator",
            "time_window",
            "insufficient_data",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be nonempty")
        if self.unit not in _UNITS:
            raise ValueError(f"unit must be one of {sorted(_UNITS)}")
        if self.denominator is not None and not self.denominator.strip():
            raise ValueError("denominator must be nonempty when supplied")


METRICS: dict[str, MetricDefinition] = {
    "gross_sales": MetricDefinition(
        "gross_sales",
        "Gross sales",
        "money",
        "SUM(quantity × unit_price)",
        "SUM(quantity × unit_price)",
        None,
        _ACTIVE_RANGE,
        "No sales in range: reported as 0.0000.",
    ),
    "orders": MetricDefinition(
        "orders",
        "Distinct orders",
        "count",
        "COUNT(DISTINCT order_id)",
        "COUNT(DISTINCT order_id)",
        None,
        _ACTIVE_RANGE,
        "No orders in range: reported as 0.",
    ),
    "units_sold": MetricDefinition(
        "units_sold",
        "Units sold",
        "count",
        "SUM(quantity)",
        "SUM(quantity)",
        None,
        _ACTIVE_RANGE,
        "No units in range: reported as 0.",
    ),
    "average_order_value": MetricDefinition(
        "average_order_value",
        "Average order value",
        "money",
        "gross_sales / orders",
        "gross_sales",
        "orders",
        _ACTIVE_RANGE,
        "no orders in range: reported as 0.0000",
    ),
    "change_percent": MetricDefinition(
        "change_percent",
        "Percentage change",
        "percent",
        "change_percent = (current_value - comparison_value) / comparison_value × 100",
        "current_value - comparison_value",
        "comparison_value",
        "The current reporting range and its selected comparison period.",
        "When the comparison value is zero, label the result New, No prior value, or No change and show the absolute change instead of an infinite percentage.",
    ),
    "product_revenue_share": MetricDefinition(
        "product_revenue_share",
        "Product revenue share",
        "percent",
        "product_revenue_share = product_gross_sales / total_gross_sales",
        "product_gross_sales",
        "total_gross_sales",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    "gross_sales_share": MetricDefinition(
        "gross_sales_share",
        "Gross-sales share",
        "percent",
        "product_gross_sales / total_gross_sales",
        "product_gross_sales",
        "total_gross_sales",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    "cumulative_share": MetricDefinition(
        "cumulative_share",
        "Cumulative gross-sales share",
        "percent",
        "running sum of product gross sales / total gross sales",
        "running sum of product gross sales",
        "total_gross_sales",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    "top_20_percent_share": MetricDefinition(
        "top_20_percent_share",
        "Top 20% product share",
        "percent",
        "cumulative gross-sales share at ceil(0.2 × product_count)",
        "gross sales of the first ceil(0.2 × product_count) products",
        "total_gross_sales",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    "products_to_80_percent": MetricDefinition(
        "products_to_80_percent",
        "Products to 80% of gross sales",
        "count",
        "smallest k where cumulative gross-sales share is at least 0.8",
        "smallest qualifying product prefix",
        "total_gross_sales",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    "cumulative_revenue_share": MetricDefinition(
        "cumulative_revenue_share",
        "Cumulative revenue share",
        "percent",
        "The running sum of product gross sales in descending gross-sales order, divided by total gross sales.",
        "Running sum of product gross sales in descending gross-sales order",
        "total gross sales",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    "weighted_unit_price": MetricDefinition(
        "weighted_unit_price",
        "Weighted realized unit price",
        "money",
        "weighted_unit_price = SUM(quantity × unit_price) / SUM(quantity)",
        "SUM(quantity × unit_price)",
        "SUM(quantity)",
        "Each automatic daily, weekly, or monthly trend bucket in the active reporting range.",
        "Unavailable when the bucket has no units sold.",
    ),
    "order_penetration": MetricDefinition(
        "order_penetration",
        "Order penetration",
        "percent",
        "order_penetration = orders_containing_product / all_orders",
        "orders_containing_product",
        "all_orders",
        _ACTIVE_RANGE,
        "Unavailable when there are no orders in the reporting range.",
    ),
    "basket_support": MetricDefinition(
        "basket_support",
        "Basket support",
        "percent",
        "support(A,B) = orders_with_A_and_B / all_orders",
        "orders_with_A_and_B",
        "all_orders",
        _ACTIVE_RANGE,
        _BASKET_INSUFFICIENT_DATA,
    ),
    "basket_confidence": MetricDefinition(
        "basket_confidence",
        "Basket confidence",
        "percent",
        "confidence(A→B) = orders_with_A_and_B / orders_with_A",
        "orders_with_A_and_B",
        "orders_with_A",
        _ACTIVE_RANGE,
        _BASKET_INSUFFICIENT_DATA,
    ),
    "basket_lift": MetricDefinition(
        "basket_lift",
        "Basket lift",
        "ratio",
        "lift(A→B) = confidence(A→B) / order_penetration(B)",
        "confidence(A→B)",
        "order_penetration(B)",
        _ACTIVE_RANGE,
        _BASKET_INSUFFICIENT_DATA,
    ),
}


def get_metric(key: str) -> MetricDefinition:
    """Return the definition for ``key`` or raise ``KeyError`` when it is unknown."""
    return METRICS[key]
