from datetime import date
from decimal import Decimal

import duckdb

_TOP_PRODUCTS_SQL = """
SELECT product_id,
       min(product_name),
       sum(quantity * unit_price) AS gross_sales,
       sum(quantity),
       count(DISTINCT order_id)
FROM line_items
WHERE order_date BETWEEN ? AND ?
GROUP BY product_id
ORDER BY gross_sales DESC, product_id ASC
LIMIT ?
"""


def read_top_products(
    connection: duckdb.DuckDBPyConnection, start: date, end: date, n: int = 10
) -> list[dict]:
    """The ``n`` best-selling products by gross sales for rows dated ``start`` to ``end``.

    Returns ``[{"product_id": str, "product_name": str, "gross_sales": Decimal,
    "units_sold": int, "distinct_orders": int}, ...]``, highest gross sales
    first; ties are broken by ``product_id`` ascending, compared as text
    (``p10`` before ``p2``). Products are grouped by ``product_id``. If an id
    ever carried several names, the alphabetically smallest is reported so the
    result stays deterministic. Fewer than ``n`` products gives a shorter list.
    Money stays ``Decimal`` end to end. Raises ``ValueError`` if ``n`` < 1.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    rows = connection.execute(_TOP_PRODUCTS_SQL, [start, end, n]).fetchall()
    return [
        {
            "product_id": product_id,
            "product_name": product_name,
            "gross_sales": Decimal(gross_sales),
            "units_sold": int(units_sold),
            "distinct_orders": int(distinct_orders),
        }
        for product_id, product_name, gross_sales, units_sold, distinct_orders in rows
    ]
