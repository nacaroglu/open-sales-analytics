from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

import duckdb

from app.analytics.products.top_products import read_product_totals
from app.analytics.shared.availability import Availability, AvailabilityState

_SHARE_STEP = Decimal("0.000001")
_EIGHTY_PERCENT = Decimal("0.8")


def read_product_share(connection: duckdb.DuckDBPyConnection, start: date, end: date) -> dict:
    """Return exact product gross-sales shares and Pareto summary values."""
    products = sorted(
        read_product_totals(connection, start, end),
        key=lambda row: (-row["gross_sales"], row["product_id"]),
    )
    if not products:
        return {
            "products": [],
            "product_count": 0,
            "total_gross_sales": Decimal("0.0000"),
            "top_20_percent_product_count": None,
            "top_20_percent_share": None,
            "products_to_80_percent": None,
            "availability": Availability(
                AvailabilityState.ZERO_RESULT, "No products have sales in the selected range."
            ),
        }

    total = sum((row["gross_sales"] for row in products), Decimal("0"))
    if total == 0:
        return {
            "products": [
                {**row, "gross_sales_share": None, "cumulative_share": None} for row in products
            ],
            "product_count": len(products),
            "total_gross_sales": total,
            "top_20_percent_product_count": None,
            "top_20_percent_share": None,
            "products_to_80_percent": None,
            "availability": Availability(
                AvailabilityState.INSUFFICIENT_DATA, "Gross sales in this range are zero."
            ),
        }

    cumulative = Decimal("0")
    enriched: list[dict] = []
    products_to_80 = None
    for row in products:
        cumulative += row["gross_sales"]
        if products_to_80 is None and cumulative / total >= _EIGHTY_PERCENT:
            products_to_80 = len(enriched) + 1
        enriched.append(
            {
                **row,
                "gross_sales_share": (row["gross_sales"] / total).quantize(
                    _SHARE_STEP, rounding=ROUND_HALF_UP
                ),
                "cumulative_share": (cumulative / total).quantize(
                    _SHARE_STEP, rounding=ROUND_HALF_UP
                ),
            }
        )
    top_count = max(1, ceil(len(products) * 0.2))
    assert products_to_80 is not None
    return {
        "products": enriched,
        "product_count": len(products),
        "total_gross_sales": total,
        "top_20_percent_product_count": top_count,
        "top_20_percent_share": enriched[top_count - 1]["cumulative_share"],
        "products_to_80_percent": products_to_80,
        "availability": Availability(AvailabilityState.AVAILABLE),
    }
