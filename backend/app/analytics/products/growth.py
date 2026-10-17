from decimal import Decimal

import duckdb

from app.analytics.shared.availability import Availability, AvailabilityState
from app.analytics.shared.periods import ComparisonPeriod, ReportingRange, compute_change

_CURRENT_ONLY_SQL = """
SELECT product_id,
       min(product_name),
       sum(quantity * unit_price),
       sum(quantity),
       count(DISTINCT order_id)
FROM line_items
WHERE order_date BETWEEN ? AND ?
GROUP BY product_id
"""
_BOTH_PERIODS_SQL = """
SELECT product_id,
       min(product_name),
       sum(CASE WHEN order_date BETWEEN ? AND ? THEN quantity * unit_price ELSE 0 END),
       sum(CASE WHEN order_date BETWEEN ? AND ? THEN quantity * unit_price ELSE 0 END),
       sum(CASE WHEN order_date BETWEEN ? AND ? THEN quantity ELSE 0 END),
       sum(CASE WHEN order_date BETWEEN ? AND ? THEN quantity ELSE 0 END),
       count(DISTINCT CASE WHEN order_date BETWEEN ? AND ? THEN order_id END),
       count(DISTINCT CASE WHEN order_date BETWEEN ? AND ? THEN order_id END),
       sum(CASE WHEN order_date BETWEEN ? AND ? THEN 1 ELSE 0 END),
       sum(CASE WHEN order_date BETWEEN ? AND ? THEN 1 ELSE 0 END)
FROM line_items
WHERE (order_date BETWEEN ? AND ?) OR (order_date BETWEEN ? AND ?)
GROUP BY product_id
"""


def _compared(current, baseline, baseline_absent: bool) -> dict:
    change = compute_change(current, baseline, "new" if baseline_absent else "no_prior_value")
    return {
        "value": current,
        "comparison_value": baseline,
        "absolute_change": change.absolute_change,
        "percent_change": change.percent_change,
        "change_status": change.status,
    }


def _row_values(row, comparison_available: bool) -> dict:
    if not comparison_available:
        product_id, product_name, gross, units, orders = row
        return {
            "product_id": product_id,
            "product_name": product_name,
            "gross_sales": {
                "value": Decimal(gross or 0),
                "comparison_value": None,
                "absolute_change": None,
                "percent_change": None,
                "change_status": None,
            },
            "units_sold": {
                "value": int(units or 0),
                "comparison_value": None,
                "absolute_change": None,
                "percent_change": None,
                "change_status": None,
            },
            "orders": {
                "value": int(orders or 0),
                "comparison_value": None,
                "absolute_change": None,
                "percent_change": None,
                "change_status": None,
            },
            "classification": None,
        }

    (
        product_id,
        product_name,
        current_gross,
        baseline_gross,
        current_units,
        baseline_units,
        current_orders,
        baseline_orders,
        current_lines,
        baseline_lines,
    ) = row
    current_gross = Decimal(current_gross or 0)
    baseline_gross = Decimal(baseline_gross or 0)
    current_units = int(current_units or 0)
    baseline_units = int(baseline_units or 0)
    current_orders = int(current_orders or 0)
    baseline_orders = int(baseline_orders or 0)
    current_present = bool(current_lines)
    baseline_present = bool(baseline_lines)
    classification = (
        "new"
        if not baseline_present
        else "no_current_sales"
        if not current_present
        else "rising"
        if current_gross > baseline_gross
        else "falling"
        if current_gross < baseline_gross
        else "unchanged"
    )
    return {
        "product_id": product_id,
        "product_name": product_name,
        "gross_sales": _compared(current_gross, baseline_gross, not baseline_present),
        "units_sold": _compared(current_units, baseline_units, not baseline_present),
        "orders": _compared(current_orders, baseline_orders, not baseline_present),
        "classification": classification,
    }


def read_product_growth(
    connection: duckdb.DuckDBPyConnection,
    current: ReportingRange,
    comparison: ComparisonPeriod,
) -> dict:
    """Compare products across the exact periods supplied by shared period logic."""
    if comparison.available:
        params = [
            current.start,
            current.end,
            comparison.comparison_start,
            comparison.comparison_end,
            current.start,
            current.end,
            comparison.comparison_start,
            comparison.comparison_end,
            current.start,
            current.end,
            comparison.comparison_start,
            comparison.comparison_end,
            current.start,
            current.end,
            comparison.comparison_start,
            comparison.comparison_end,
            current.start,
            current.end,
            comparison.comparison_start,
            comparison.comparison_end,
        ]
        rows = connection.execute(_BOTH_PERIODS_SQL, params).fetchall()
    else:
        rows = connection.execute(_CURRENT_ONLY_SQL, [current.start, current.end]).fetchall()

    products = []
    for row in rows:
        products.append(_row_values(row, comparison.available))
    products.sort(key=lambda product: product["product_id"])
    if not products:
        availability = Availability(
            AvailabilityState.ZERO_RESULT, "No products have sales in the selected ranges."
        )
    else:
        availability = Availability(AvailabilityState.AVAILABLE)
    rising = [
        product
        for product in products
        if product["gross_sales"]["absolute_change"] is not None
        and product["gross_sales"]["absolute_change"] > 0
    ]
    falling = [
        product
        for product in products
        if product["gross_sales"]["absolute_change"] is not None
        and product["gross_sales"]["absolute_change"] < 0
    ]
    rising.sort(
        key=lambda product: (-product["gross_sales"]["absolute_change"], product["product_id"])
    )
    falling.sort(
        key=lambda product: (product["gross_sales"]["absolute_change"], product["product_id"])
    )
    return {
        "availability": availability,
        "products": products,
        "rising": rising[:10],
        "falling": falling[:10],
    }
