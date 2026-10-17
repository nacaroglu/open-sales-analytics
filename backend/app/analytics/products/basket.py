from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import duckdb

from app.analytics.shared.availability import Availability, AvailabilityState
from app.analytics.shared.metrics import (
    BASKET_MIN_SHARED_ORDERS,
    BASKET_MIN_SUPPORT,
    MAX_DISTINCT_PRODUCTS_PER_ORDER,
)

_SIX_PLACES = Decimal("0.000001")

_BASKET_SQL = """
WITH range_lines AS (
    SELECT order_id, product_id, min(product_name) AS product_name
    FROM line_items
    WHERE order_date BETWEEN ? AND ?
    GROUP BY order_id, product_id
), oversize_orders AS (
    SELECT order_id
    FROM range_lines
    GROUP BY order_id
    HAVING count(*) > ?
), in_range AS (
    SELECT range_lines.*
    FROM range_lines
    WHERE NOT EXISTS (
        SELECT 1 FROM oversize_orders WHERE oversize_orders.order_id = range_lines.order_id
    )
), basket_population AS (
    SELECT count(*) AS basket_orders
    FROM (SELECT DISTINCT order_id FROM in_range)
), product_orders AS (
    SELECT product_id, min(product_name) AS product_name, count(*) AS orders_with_product
    FROM in_range
    GROUP BY product_id
), pair_counts AS (
    SELECT a.product_id AS product_a_id,
           a.product_name AS product_a_name,
           b.product_id AS product_b_id,
           b.product_name AS product_b_name,
           count(*) AS shared_orders
    FROM in_range a
    JOIN in_range b ON a.order_id = b.order_id AND a.product_id < b.product_id
    GROUP BY a.product_id, a.product_name, b.product_id, b.product_name
), eligible_pairs AS (
    SELECT pc.*,
           pa.orders_with_product AS orders_with_a,
           pb.orders_with_product AS orders_with_b,
           bp.basket_orders
    FROM pair_counts pc
    JOIN product_orders pa ON pa.product_id = pc.product_a_id
    JOIN product_orders pb ON pb.product_id = pc.product_b_id
    CROSS JOIN basket_population bp
    WHERE pc.shared_orders >= ?
      AND CAST(pc.shared_orders AS DECIMAL(18,6)) / NULLIF(bp.basket_orders, 0) >= ?
)
SELECT product_a_id,
       product_a_name,
       product_b_id,
       product_b_name,
       shared_orders,
       orders_with_a,
       orders_with_b,
       bp.basket_orders,
       (SELECT count(*) FROM oversize_orders) AS excluded_oversize_orders
FROM basket_population bp
LEFT JOIN eligible_pairs ep ON TRUE
"""


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) / Decimal(denominator)).quantize(_SIX_PLACES, rounding=ROUND_HALF_UP)


def _availability(
    basket_orders: int, eligible_pair_count: int, excluded_oversize_orders: int
) -> Availability:
    if basket_orders == 0:
        if excluded_oversize_orders:
            return Availability(
                AvailabilityState.INSUFFICIENT_DATA,
                "All orders in this range have more than 100 products and are excluded from basket analysis",
            )
        return Availability(AvailabilityState.ZERO_RESULT, "No orders in the selected range.")
    if basket_orders < BASKET_MIN_SHARED_ORDERS:
        return Availability(
            AvailabilityState.INSUFFICIENT_DATA,
            "At least 10 orders are needed for basket analysis",
        )
    if eligible_pair_count == 0:
        return Availability(
            AvailabilityState.ZERO_RESULT, "No eligible product pairs in the selected range."
        )
    return Availability(AvailabilityState.AVAILABLE)


def read_product_basket(
    connection: duckdb.DuckDBPyConnection,
    start: date,
    end: date,
    product_id: str | None = None,
) -> dict:
    """Return thresholded product pairs and optionally related products for one product."""
    rows = connection.execute(
        _BASKET_SQL,
        [
            start,
            end,
            MAX_DISTINCT_PRODUCTS_PER_ORDER,
            BASKET_MIN_SHARED_ORDERS,
            BASKET_MIN_SUPPORT,
        ],
    ).fetchall()
    basket_orders = int(rows[0][7]) if rows else 0
    excluded_oversize_orders = int(rows[0][8]) if rows else 0
    pairs: list[dict[str, Any]] = []
    for (
        product_a_id,
        product_a_name,
        product_b_id,
        product_b_name,
        shared_orders,
        orders_with_a,
        orders_with_b,
        basket_orders,
        _excluded_oversize_orders,
    ) in rows:
        if product_a_id is None:
            continue
        shared_orders = int(shared_orders)
        orders_with_a = int(orders_with_a)
        orders_with_b = int(orders_with_b)
        basket_orders = int(basket_orders)
        support = Decimal(shared_orders) / Decimal(basket_orders)
        confidence_a_to_b = Decimal(shared_orders) / Decimal(orders_with_a)
        confidence_b_to_a = Decimal(shared_orders) / Decimal(orders_with_b)
        lift = confidence_a_to_b / (Decimal(orders_with_b) / Decimal(basket_orders))
        pairs.append(
            {
                "product_a": {"product_id": product_a_id, "product_name": product_a_name},
                "product_b": {"product_id": product_b_id, "product_name": product_b_name},
                "shared_orders": shared_orders,
                "support": support.quantize(_SIX_PLACES, rounding=ROUND_HALF_UP),
                "confidence_a_to_b": confidence_a_to_b.quantize(
                    _SIX_PLACES, rounding=ROUND_HALF_UP
                ),
                "confidence_b_to_a": confidence_b_to_a.quantize(
                    _SIX_PLACES, rounding=ROUND_HALF_UP
                ),
                "lift": lift.quantize(_SIX_PLACES, rounding=ROUND_HALF_UP),
                "_lift_exact": lift,
                "_basket_orders": basket_orders,
            }
        )
    pairs.sort(
        key=lambda pair: (
            -pair["_lift_exact"],
            -pair["shared_orders"],
            pair["product_a"]["product_id"],
            pair["product_b"]["product_id"],
        )
    )
    for pair in pairs:
        pair.pop("_lift_exact")
        pair.pop("_basket_orders")
    availability = _availability(basket_orders, len(pairs), excluded_oversize_orders)
    related = []
    if product_id is not None:
        for pair in pairs:
            if pair["product_a"]["product_id"] == product_id:
                related.append(
                    {
                        "product": pair["product_b"],
                        "shared_orders": pair["shared_orders"],
                        "support": pair["support"],
                        "confidence_from_x": pair["confidence_a_to_b"],
                        "confidence_to_x": pair["confidence_b_to_a"],
                        "lift": pair["lift"],
                    }
                )
            elif pair["product_b"]["product_id"] == product_id:
                related.append(
                    {
                        "product": pair["product_a"],
                        "shared_orders": pair["shared_orders"],
                        "support": pair["support"],
                        "confidence_from_x": pair["confidence_b_to_a"],
                        "confidence_to_x": pair["confidence_a_to_b"],
                        "lift": pair["lift"],
                    }
                )
    return {
        "basket_orders": basket_orders,
        "excluded_oversize_orders": excluded_oversize_orders,
        "eligible_pair_count": len(pairs),
        "pairs": pairs[:20],
        "availability": availability,
        "related_products": related[:10],
        "related_availability": (
            Availability(AvailabilityState.AVAILABLE)
            if related
            else Availability(
                AvailabilityState.ZERO_RESULT, "No eligible related products in the selected range."
            )
        ),
    }
