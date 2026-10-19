"""Authoritative metric definitions shared by APIs, tests, and UI labels."""

from dataclasses import dataclass
from decimal import Decimal

_UNITS = frozenset({"money", "count", "ratio", "percent", "days", "date"})
_ACTIVE_RANGE = "The active reporting range, inclusive of its start and end dates."
DORMANCY_WINDOWS = (30, 60, 90)
BASKET_MIN_SHARED_ORDERS = 10
BASKET_MIN_SUPPORT = Decimal("0.001")
MAX_DISTINCT_PRODUCTS_PER_ORDER = 100

PROJECTION_HISTORY_MONTHS = 18
PROJECTION_MIN_IDENTIFIED_CUSTOMERS = 500
PROJECTION_MIN_CUSTOMER_COVERAGE = Decimal("0.7000")
PROJECTION_MATURE_COHORTS = 5
PROJECTION_HORIZON_MONTHS = 12

PROJECTION_CONDITION_LABELS = {
    "history_months": "At least 18 months of order history",
    "identified_customers": "At least 500 identified customers",
    "customer_coverage": "Customer coverage of at least 70%",
    "mature_cohorts": "At least 5 monthly cohorts with 12 months of observed behaviour",
}

FIRST_PURCHASE_DEFINITION = (
    "A customer's earliest order date across the complete uploaded history; all orders on "
    "that date are first-purchase orders."
)
ACQUISITION_COHORT_DEFINITION = (
    "The calendar month containing the customer's first purchase date, represented by the "
    "month's first day."
)


@dataclass(frozen=True)
class RfmSegmentRule:
    """One named RFM segment: a rule on R and FM = F + M, with inclusive bounds."""

    name: str
    rule: str
    explanation: str
    min_r: int
    max_r: int
    min_fm: int
    max_fm: int

    def matches(self, r: int, f: int, m: int) -> bool:
        return self.min_r <= r <= self.max_r and self.min_fm <= f + m <= self.max_fm


RFM_MIN_CUSTOMERS = 5
CONCENTRATION_MIN_CUSTOMERS = 10
RFM_SCORE_FORMULA = (
    "Per dimension, values are ordered worst to best (recency: more days is worse; frequency "
    "and monetary: lower is worse); worse = customers with a strictly worse value, ties = "
    "customers with the same value (itself included), N = population size; "
    "score = floor(5 × (2 × worse + ties) / (2 × N)) + 1, in integer arithmetic (1-5). "
    "When every customer has the same value in a dimension, all get 3."
)
# Ordered: the first matching rule wins. FM = F + M (2-10).
RFM_SEGMENTS = (
    RfmSegmentRule(
        "Champions",
        "R ≥ 4 and FM ≥ 8",
        "Bought recently, often and for a lot compared with the other customers.",
        4,
        5,
        8,
        10,
    ),
    RfmSegmentRule(
        "Loyal",
        "R ≥ 3 and FM ≥ 6",
        "Buy regularly and spend well, and have not lapsed.",
        3,
        5,
        6,
        10,
    ),
    RfmSegmentRule(
        "Potential Loyalists",
        "R ≥ 4 and FM ≤ 5",
        "Bought recently but not yet often or for much.",
        4,
        5,
        2,
        5,
    ),
    RfmSegmentRule(
        "Needs Attention",
        "R = 3 and FM ≤ 5",
        "Middling recency with few or small purchases.",
        3,
        3,
        2,
        5,
    ),
    RfmSegmentRule(
        "At Risk",
        "R ≤ 2 and FM ≥ 6",
        "Used to buy often or for a lot but have not bought for a while.",
        1,
        2,
        6,
        10,
    ),
    RfmSegmentRule(
        "Lost",
        "R ≤ 2 and FM ≤ 5",
        "Have not bought for a while and bought rarely or for little.",
        1,
        2,
        2,
        5,
    ),
)
RFM_NOTE = (
    "RFM segments are relative to the customer base of this upload; they are not universal "
    "benchmarks."
)

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
    "first_purchase": MetricDefinition(
        "first_purchase",
        "First purchase",
        "date",
        FIRST_PURCHASE_DEFINITION,
        "MIN(order_date) across full history",
        None,
        "Complete uploaded history, independent of reporting range.",
        "No identified customer orders: no customer fact exists.",
    ),
    "acquisition_cohort": MetricDefinition(
        "acquisition_cohort",
        "Acquisition cohort",
        "date",
        ACQUISITION_COHORT_DEFINITION,
        "first day of the month containing first purchase",
        None,
        "Complete uploaded history, independent of reporting range.",
        "No identified customer orders: no customer fact exists.",
    ),
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
    "product_growth": MetricDefinition(
        "product_growth",
        "Product gross-sales growth",
        "money",
        "current product gross sales - comparison product gross sales",
        "current product gross sales - comparison product gross sales",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "rising_products": MetricDefinition(
        "rising_products",
        "Rising products",
        "count",
        "products with positive absolute gross-sales change",
        "count of products with positive gross-sales change",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "falling_products": MetricDefinition(
        "falling_products",
        "Falling products",
        "count",
        "products with negative absolute gross-sales change",
        "count of products with negative gross-sales change",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "new_products": MetricDefinition(
        "new_products",
        "New products",
        "count",
        "products present in the current period and absent in comparison",
        "count of products classified as new",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "no_current_sales_products": MetricDefinition(
        "no_current_sales_products",
        "Products with no current sales",
        "count",
        "products present in comparison and absent in the current period",
        "count of products classified as no_current_sales",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "unchanged_products": MetricDefinition(
        "unchanged_products",
        "Unchanged products",
        "count",
        "products whose gross sales are equal across periods",
        "count of products classified as unchanged",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "growth_rank_absolute_change": MetricDefinition(
        "growth_rank_absolute_change",
        "Product growth rank",
        "money",
        "rank by absolute gross-sales change, descending for rising and ascending for falling",
        "absolute gross-sales change",
        None,
        "The active reporting range and its selected comparison period.",
        "Unavailable when the selected comparison period is unavailable.",
    ),
    "dormancy": MetricDefinition(
        "dormancy",
        "Dormant products",
        "count",
        "a product is dormant when anchor - last_sale_date is at least the selected window",
        "count of products with days_inactive >= selected window",
        None,
        "The selected range end date as anchor, with a 30, 60, or 90 day inclusive window.",
        "Insufficient when the dataset covers fewer than the selected window before the anchor.",
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
        "basket_orders",
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
    "identified_customers": MetricDefinition(
        "identified_customers",
        "Identified customers",
        "count",
        "COUNT(DISTINCT customer_id) for identified orders in the active range",
        "COUNT(DISTINCT customer_id)",
        None,
        "The active reporting range, inclusive of its start and end dates.",
        "No identified customers in range: reported as 0 with zero_result availability.",
    ),
    "customer_coverage": MetricDefinition(
        "customer_coverage",
        "Customer coverage",
        "ratio",
        "identified distinct orders / all distinct orders",
        "Distinct orders with at least one identified customer_id",
        "All distinct orders in the dataset or selected range",
        "Dataset coverage determines the tier; range coverage describes the selected range.",
        "No customer_id column is unavailable; below 50% is suppressed; zero orders have null coverage.",
    ),
    "new_vs_returning": MetricDefinition(
        "new_vs_returning",
        "New versus returning customer gross sales",
        "money",
        "identified gross sales split into new sales on first_order_date and returning sales after first_order_date",
        "SUM(quantity × unit_price) for identified line items classified by full-history first_order_date",
        None,
        "The active reporting range, with customer first_order_date taken from complete uploaded history.",
        "No identified rows in range: all values are 0.0000 with zero_result availability; unavailable comparisons have null comparison fields.",
    ),
    "repeat_purchase": MetricDefinition(
        "repeat_purchase",
        "Repeat-purchase rate",
        "ratio",
        "repeat_customers / active_customers",
        "Active identified customers with at least 2 distinct order_ids dated on or before the range end, including orders before the range start",
        "Identified customers with at least one order in the active range (active_customers)",
        "Activity in the active reporting range; orders counted from the start of the upload through the range end, orders after the end ignored.",
        "No active identified customers in range: rate is null with insufficient_data availability; active customers but none repeating: rate 0 with zero_result availability.",
    ),
    "days_between_purchases": MetricDefinition(
        "days_between_purchases",
        "Days between purchases",
        "days",
        "Median of the included intervals (mean of the two middle values when the count is even; no mean is reported) plus counts and shares in fixed inclusive buckets: 0, 1-7, 8-14, 15-30, 31-60, 61-90, 91-180, 181-365, 366+ days",
        "Intervals: calendar days between consecutive distinct identified orders of one customer, each order dated by its first line (order_facts.first_order_date); same-day orders give 0",
        None,
        "An interval is included when its later order is dated inside the range (both ends included); its earlier order may be before the range start; orders after the range end are ignored.",
        "No included interval (no identified repeat orders in the range): median_days null, interval_count 0, every bucket share null, insufficient_data availability.",
    ),
    "cohort_retention": MetricDefinition(
        "cohort_retention",
        "Cohort retention",
        "ratio",
        "retained_count / cohort_size for each acquisition cohort and month offset N (0 = acquisition month); each cell is complete (whole month on or before the data cutoff), partial (month contains the cutoff, counts so far) or not_observed (month starts after the cutoff; count and retention null)",
        "Cohort members with at least one identified line (line_items.order_date) in calendar month acquisition_month + N, dated on or before the data cutoff",
        "Cohort size: identified customers whose acquisition_month (month of the full-history first order date) is the cohort month and whose first order is on or before the range end",
        "Rows are the acquisition months from the month containing the range start to the month containing the range end; the data cutoff is the range end. Activity before the range start still counts; activity after the cutoff is ignored.",
        "No acquisition cohort overlaps the range: rows empty, insufficient_data availability. Months after the cutoff are not_observed with null values, never 0.",
    ),
    "historical_customer_value": MetricDefinition(
        "historical_customer_value",
        "Historical Customer Value",
        "money",
        "average = total observed value / customer_count; median of per-customer values (mean of the two middle values for an even count); per cohort and month offset N: cumulative cohort gross sales from the acquisition month through the end of month acquisition_month + N (capped at the data cutoff) / cohort_size; all-cohorts curve: summed cumulative sales of cohorts whose cell N is complete / sum of their cohort sizes. Observed sales only, not a forecast.",
        "Observed identified gross sales: SUM(quantity × unit_price) over the members' identified line_items dated on or before the data cutoff, including lines before the range start",
        "Members (customer_count, or cohort_size per cohort): identified customers whose acquisition_month is from the month containing the range start to the month containing the range end and whose first order is on or before the range end",
        "Members are selected exactly as the cohort_retention rows; the data cutoff is the range end. Sales before the range start count; sales after the cutoff are ignored. Current range only, no comparison.",
        "No acquisition cohort overlaps the range: customer_count 0, average and median null, rows and all_cohorts empty, insufficient_data availability. Members whose total value is 0: values 0.0000 with zero_result availability. not_observed cells are null; an all-cohorts offset with no complete cohort is null.",
    ),
    "projected_customer_value": MetricDefinition(
        "projected_customer_value",
        "Projected 12-Month Customer Value",
        "money",
        "Weighted observed value plus mature-cohort incremental value for age months 0 through 11.",
        "SUM(customer_count × per-customer observed or projected value)",
        "SUM(customer_count)",
        "Full identified customer history through the selected data cutoff.",
        "Only eligible datasets with 18 months, 500 identified customers, 70% coverage and five mature cohorts.",
    ),
    "rfm": MetricDefinition(
        "rfm",
        "RFM segments",
        "count",
        RFM_SCORE_FORMULA
        + " Segments (FM = F + M, first matching rule wins): "
        + "; ".join(
            f"{segment.name}: {segment.rule} ({segment.explanation})" for segment in RFM_SEGMENTS
        )
        + ". Share = segment customer_count / N.",
        "Customers per segment. Inputs per customer, from identified lines dated on or before the range end: recency = days from the latest line date to the range end; frequency = distinct order_ids; monetary = SUM(quantity × unit_price)",
        "N: identified customers with at least one identified order on or before the range end",
        "All identified activity through the selected end date; the range start has no effect. Current range only, no comparison. "
        + RFM_NOTE,
        f"Fewer than {RFM_MIN_CUSTOMERS} customers: segments empty, insufficient_data availability. "
        + RFM_NOTE,
    ),
    "rfm_drilldown": MetricDefinition(
        "rfm_drilldown",
        "RFM segment drill-downs",
        "count",
        "Per RFM segment (the rfm scoring and segments, all six in fixed order): customer_count; "
        "gross_sales = SUM(monetary) of its members; gross_sales_share = segment gross_sales / "
        "total gross_sales (null when the total is 0); recency_distribution = members per "
        "recency bucket (0-30, 31-60, 61-90, 91-180, 181-365, 366+ days); "
        "frequency_distribution = members per distinct-order bucket (1, 2, 3, 4, 5, 6-10, "
        "11-20, 21+). Aggregates only, no customer identifiers.",
        "Customers and their monetary (SUM(quantity × unit_price) of identified lines dated on "
        "or before the range end) per segment and bucket",
        "N and total gross_sales: identified customers with at least one identified order on "
        "or before the range end, and the sum of their monetary values",
        "All identified activity through the selected end date; the range start has no effect. "
        "Current range only, no comparison. " + RFM_NOTE,
        f"Fewer than {RFM_MIN_CUSTOMERS} customers: segments empty, insufficient_data "
        "availability; customer_count and gross_sales still report the real totals. " + RFM_NOTE,
    ),
    "purchase_frequency": MetricDefinition(
        "purchase_frequency",
        "Purchase frequency",
        "count",
        "Customers grouped by their distinct identified order count through the selected end date "
        "into fixed buckets: 1, 2, 3, 4, 5, 6-10, 11-20 and 21+.",
        "Identified customers in each distinct-order bucket",
        "Identified customers with at least one order on or before the selected end date",
        "All identified orders through the selected end date; the range start has no effect. Current range only, no comparison.",
        "No identified customers on or before the selected end date: all bucket counts are 0, shares are null, and availability is insufficient_data.",
    ),
    "concentration": MetricDefinition(
        "concentration",
        "Customer concentration",
        "ratio",
        "top_decile_gross_sales / identified_gross_sales, where the top decile has ceil(N / 10) customers ranked by range gross sales",
        "SUM of the ceil(N / 10) largest identified customer gross-sales values in the active range",
        "SUM(quantity × unit_price) for all identified line items in the active range",
        _ACTIVE_RANGE,
        "Fewer than 10 identified customers, or zero identified gross sales: share is null with insufficient_data availability.",
    ),
}


def get_metric(key: str) -> MetricDefinition:
    """Return the definition for ``key`` or raise ``KeyError`` when it is unknown."""
    return METRICS[key]
