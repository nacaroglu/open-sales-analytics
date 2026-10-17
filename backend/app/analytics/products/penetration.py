from collections.abc import Collection
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import duckdb

from app.analytics.shared.availability import Availability, AvailabilityState

_SIX_PLACES = Decimal("0.000001")


def read_product_penetration(
    connection: duckdb.DuckDBPyConnection,
    start: date,
    end: date,
    order_population: Collection[str] | None = None,
    product_id: str | None = None,
) -> dict:
    """Return product order penetration for all products or one product.

    ``order_population`` can narrow the denominator and numerator to a caller-selected
    set of order ids, such as a future basket-eligible population.
    """
    population = None if order_population is None else frozenset(order_population)
    if population is None:
        population_row = connection.execute(
            """
            SELECT count(DISTINCT order_id)
            FROM line_items
            WHERE order_date BETWEEN ? AND ?
            """,
            [start, end],
        ).fetchone()
        assert population_row is not None
        all_orders = int(population_row[0])
    else:
        all_orders = len(population)

    conditions = ["order_date BETWEEN ? AND ?"]
    params: list[object] = [start, end]
    if product_id is not None:
        conditions.append("product_id = ?")
        params.append(product_id)
    if population is not None:
        if not population:
            rows = []
        else:
            placeholders = ", ".join("?" for _ in population)
            conditions.append(f"order_id IN ({placeholders})")
            params.extend(sorted(population))
            rows = connection.execute(
                f"""
                SELECT product_id, min(product_name), count(DISTINCT order_id)
                FROM line_items
                WHERE {" AND ".join(conditions)}
                GROUP BY product_id
                """,
                params,
            ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT product_id, min(product_name), count(DISTINCT order_id)
            FROM line_items
            WHERE {" AND ".join(conditions)}
            GROUP BY product_id
            """,
            params,
        ).fetchall()

    if product_id is not None and not rows:
        product_name_row = connection.execute(
            "SELECT min(product_name) FROM line_items WHERE product_id = ?",
            [product_id],
        ).fetchone()
        assert product_name_row is not None
        product_name = product_name_row[0]
        if product_name is not None:
            rows = [(product_id, product_name, 0)]

    products = []
    for row_product_id, product_name, containing_orders in rows:
        containing_orders = int(containing_orders)
        ratio = (
            None
            if all_orders == 0
            else (Decimal(containing_orders) / Decimal(all_orders)).quantize(
                _SIX_PLACES, rounding=ROUND_HALF_UP
            )
        )
        products.append(
            {
                "product_id": row_product_id,
                "product_name": product_name,
                "orders_containing_product": containing_orders,
                "all_orders": all_orders,
                "order_penetration": ratio,
            }
        )
    products.sort(
        key=lambda product: (
            -product["order_penetration"] if product["order_penetration"] is not None else 0,
            product["product_id"],
        )
    )
    has_orders = all_orders > 0
    return {
        "all_orders": all_orders,
        "availability": Availability(
            AvailabilityState.AVAILABLE
            if has_orders and (products or product_id is not None)
            else AvailabilityState.ZERO_RESULT,
            None
            if has_orders and (products or product_id is not None)
            else "No orders in the selected range.",
        ),
        "products": products,
    }
