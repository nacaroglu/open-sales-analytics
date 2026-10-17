from datetime import date
from decimal import Decimal
from typing import TypedDict

import duckdb

from app.analytics.shared.availability import Availability, AvailabilityState
from app.analytics.shared.metrics import DORMANCY_WINDOWS
from app.analytics.shared.periods import ReportingRange, recency_anchor

_DORMANT_PRODUCTS_SQL = """
WITH dataset_bounds AS (
    SELECT min(order_date) AS dataset_first_date
    FROM line_items
), product_history AS (
    SELECT product_id,
           min(product_name) AS product_name,
           max(order_date) AS last_sale_date,
           sum(quantity * unit_price) AS earlier_gross_sales,
           count(DISTINCT order_id) AS earlier_orders
    FROM line_items
    WHERE order_date <= ?
    GROUP BY product_id
)
SELECT product_id,
       product_name,
       last_sale_date,
       earlier_gross_sales,
       earlier_orders,
       dataset_first_date
FROM product_history
CROSS JOIN dataset_bounds
"""


class DormantProduct(TypedDict):
    product_id: str
    product_name: str
    last_sale_date: date
    days_inactive: int
    earlier_gross_sales: Decimal
    earlier_orders: int


def read_dormant_products(
    connection: duckdb.DuckDBPyConnection,
    reporting_range: ReportingRange,
    window_days: int,
) -> dict:
    """Return every product inactive for the selected window at the range anchor."""
    if window_days not in DORMANCY_WINDOWS:
        raise ValueError("window_days must be 30, 60 or 90")

    anchor = recency_anchor(reporting_range)
    rows = connection.execute(_DORMANT_PRODUCTS_SQL, [anchor]).fetchall()
    if not rows:
        return {
            "window_days": window_days,
            "anchor_date": anchor,
            "availability": Availability(
                AvailabilityState.ZERO_RESULT, "No dormant products in the selected range."
            ),
            "products": [],
        }

    dataset_first_date = rows[0][5]
    if (anchor - dataset_first_date).days < window_days:
        return {
            "window_days": window_days,
            "anchor_date": anchor,
            "availability": Availability(
                AvailabilityState.INSUFFICIENT_DATA,
                f"The data covers fewer than {window_days} days before {anchor}.",
            ),
            "products": [],
        }

    products: list[DormantProduct] = []
    for product_id, product_name, last_sale_date, gross_sales, orders, _ in rows:
        days_inactive = (anchor - last_sale_date).days
        if days_inactive >= window_days:
            products.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "last_sale_date": last_sale_date,
                    "days_inactive": days_inactive,
                    "earlier_gross_sales": gross_sales,
                    "earlier_orders": int(orders),
                }
            )
    products.sort(key=lambda product: (-product["earlier_gross_sales"], product["product_id"]))
    return {
        "window_days": window_days,
        "anchor_date": anchor,
        "availability": Availability(
            AvailabilityState.AVAILABLE if products else AvailabilityState.ZERO_RESULT,
            None if products else "No dormant products in the selected range.",
        ),
        "products": products,
    }
