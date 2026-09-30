from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import duckdb

_MONEY_STEP = Decimal("0.0001")
_ZERO_MONEY = Decimal("0.0000")
_KPI_SQL = """
SELECT sum(quantity * unit_price),
       count(DISTINCT order_id),
       sum(quantity)
FROM line_items
WHERE order_date BETWEEN ? AND ?
"""


def read_kpis(connection: duckdb.DuckDBPyConnection, start: date, end: date) -> dict:
    """The four KPI values for rows dated from ``start`` to ``end``, both included.

    Returns ``{"gross_sales": Decimal, "orders": int, "units_sold": int,
    "average_order_value": Decimal}``. Money stays ``Decimal`` end to end; the
    average is rounded half-up to four places. An empty range gives zeros.
    """
    kpi_row = connection.execute(_KPI_SQL, [start, end]).fetchone()
    assert kpi_row is not None  # an aggregate query always returns one row
    gross_sales, orders, units_sold = kpi_row
    orders = int(orders)
    units_sold = int(units_sold or 0)
    gross_sales = Decimal(gross_sales) if gross_sales is not None else _ZERO_MONEY

    if orders == 0:
        average_order_value = _ZERO_MONEY
    else:
        average_order_value = (gross_sales / orders).quantize(_MONEY_STEP, rounding=ROUND_HALF_UP)

    return {
        "gross_sales": gross_sales,
        "orders": orders,
        "units_sold": units_sold,
        "average_order_value": average_order_value,
    }
