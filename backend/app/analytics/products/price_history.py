from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import duckdb

from app.analytics.shared.availability import Availability, AvailabilityState
from app.analytics.shared.buckets import _bucket_start, _next_bucket

_FOUR_PLACES = Decimal("0.0001")


def read_product_price_history(
    connection: duckdb.DuckDBPyConnection,
    product_id: str,
    start: date,
    end: date,
    granularity: str,
) -> dict:
    """Return contiguous weighted realized-price buckets for one product."""
    rows = connection.execute(
        """
        SELECT order_date,
               sum(quantity * unit_price),
               sum(quantity)
        FROM line_items
        WHERE product_id = ? AND order_date BETWEEN ? AND ?
        GROUP BY order_date
        """,
        [product_id, start, end],
    ).fetchall()
    totals: dict[date, tuple[Decimal, int]] = {}
    for order_date, amount, units in rows:
        bucket = _bucket_start(order_date, granularity)
        previous_amount, previous_units = totals.get(bucket, (Decimal("0.0000"), 0))
        totals[bucket] = (previous_amount + Decimal(amount), previous_units + int(units))

    buckets = []
    bucket = _bucket_start(start, granularity)
    while bucket <= end:
        amount, units = totals.get(bucket, (Decimal("0.0000"), 0))
        price = (
            None
            if units == 0
            else (amount / Decimal(units)).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
        )
        buckets.append(
            {
                "bucket_start": bucket,
                "weighted_unit_price": price,
                "units_sold": units,
            }
        )
        bucket = _next_bucket(bucket, granularity)
    return {
        "granularity": granularity,
        "availability": Availability(
            AvailabilityState.AVAILABLE
            if any(row["units_sold"] for row in buckets)
            else AvailabilityState.ZERO_RESULT,
            None
            if any(row["units_sold"] for row in buckets)
            else "The product has no sales in the selected range.",
        ),
        "buckets": buckets,
    }
