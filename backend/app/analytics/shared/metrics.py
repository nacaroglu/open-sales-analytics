"""Authoritative metric definitions shared by APIs, tests, and UI labels."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    """The stable, documented contract for one analytics metric."""

    key: str
    label: str
    unit: str
    formula: str
    numerator: str
    denominator: str | None
    text: str | None
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
        if self.denominator is not None and not self.denominator.strip():
            raise ValueError("denominator must be nonempty when supplied")
        if self.text is not None and not self.text.strip():
            raise ValueError("text must be nonempty when supplied")


_ACTIVE_RANGE = "Active reporting range, inclusive of its start and end dates."
_ZERO_BASELINE = "When the comparison value is zero, show the absolute change and New, No prior value, or No change instead of an infinite percentage."
_BASKET_LIMITS = "Pairs require at least 10 shared orders and 0.1% support; orders containing more than 100 distinct products are excluded from basket analysis only."

METRICS = (
    MetricDefinition(
        "gross_sales",
        "Gross sales",
        "currency",
        "SUM(quantity × unit_price)",
        "SUM(quantity × unit_price)",
        None,
        "Sales before discounts, refunds, and costs, which are outside Phase 3.",
        _ACTIVE_RANGE,
        "Returns zero when no line items fall in the reporting range.",
    ),
    MetricDefinition(
        "orders",
        "Distinct orders",
        "orders",
        "COUNT(DISTINCT order_id)",
        "COUNT(DISTINCT order_id)",
        None,
        None,
        _ACTIVE_RANGE,
        "Returns zero when no line items fall in the reporting range.",
    ),
    MetricDefinition(
        "units_sold",
        "Units sold",
        "units",
        "SUM(quantity)",
        "SUM(quantity)",
        None,
        None,
        _ACTIVE_RANGE,
        "Returns zero when no line items fall in the reporting range.",
    ),
    MetricDefinition(
        "average_order_value",
        "Average order value",
        "currency",
        "gross_sales / distinct_orders",
        "gross_sales",
        "distinct_orders",
        "Rounded half-up to four decimal places.",
        _ACTIVE_RANGE,
        "Returns zero when there are no distinct orders.",
    ),
    MetricDefinition(
        "change_percent",
        "Percentage change",
        "percent",
        "(current_value - comparison_value) / comparison_value × 100",
        "current_value - comparison_value",
        "comparison_value",
        None,
        "The current reporting range and its selected comparison period.",
        _ZERO_BASELINE,
    ),
    MetricDefinition(
        "product_revenue_share",
        "Product revenue share",
        "percent",
        "product_gross_sales / total_gross_sales",
        "product_gross_sales",
        "total_gross_sales",
        None,
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    MetricDefinition(
        "cumulative_product_revenue_share",
        "Cumulative product revenue share",
        "percent",
        "running descending product_gross_sales / total_gross_sales",
        "Running product gross sales ordered by descending gross sales",
        "total_gross_sales",
        "Products are ordered by gross sales before calculating the running share.",
        _ACTIVE_RANGE,
        "Unavailable when total gross sales is zero.",
    ),
    MetricDefinition(
        "weighted_unit_price",
        "Weighted realized unit price",
        "currency per unit",
        "SUM(quantity × unit_price) / SUM(quantity)",
        "SUM(quantity × unit_price)",
        "SUM(quantity)",
        None,
        "Each automatic daily, weekly, or monthly trend bucket in the active reporting range.",
        "Unavailable when the bucket has no units sold.",
    ),
    MetricDefinition(
        "order_penetration",
        "Order penetration",
        "percent",
        "orders_containing_product / all_orders",
        "orders_containing_product",
        "all_orders",
        None,
        _ACTIVE_RANGE,
        "Unavailable when there are no orders in the reporting range.",
    ),
    MetricDefinition(
        "basket_support",
        "Basket support",
        "percent",
        "orders_with_A_and_B / all_orders",
        "orders_with_A_and_B",
        "all_orders",
        _BASKET_LIMITS,
        _ACTIVE_RANGE,
        "Unavailable unless the pair meets the stated evidence thresholds.",
    ),
    MetricDefinition(
        "basket_confidence",
        "Basket confidence",
        "percent",
        "orders_with_A_and_B / orders_with_A",
        "orders_with_A_and_B",
        "orders_with_A",
        _BASKET_LIMITS,
        _ACTIVE_RANGE,
        "Unavailable unless the pair meets the stated evidence thresholds.",
    ),
    MetricDefinition(
        "basket_lift",
        "Basket lift",
        "ratio",
        "confidence(A→B) / order_penetration(B)",
        "confidence(A→B)",
        "order_penetration(B)",
        _BASKET_LIMITS,
        _ACTIVE_RANGE,
        "Unavailable unless the pair meets the stated evidence thresholds.",
    ),
)

METRIC_BY_KEY = {metric.key: metric for metric in METRICS}
