"""New-versus-returning customer revenue analytics."""

from datetime import date
from decimal import Decimal

import duckdb

_ZERO_MONEY = Decimal("0.0000")


def read_new_vs_returning(
    connection: duckdb.DuckDBPyConnection, start: date, end: date
) -> dict[str, Decimal | int]:
    """Split identified gross sales using each customer's full-history first date.

    The reporting range filters line dates, while ``customer_facts`` supplies the
    unfiltered acquisition date. This keeps a later reporting-range start from
    reclassifying an existing customer as new.
    """
    row = connection.execute(
        """
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN li.order_date = cf.first_order_date
                        THEN li.quantity * li.unit_price
                        ELSE 0
                    END
                ),
                CAST(0 AS DECIMAL(38, 4))
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN li.order_date > cf.first_order_date
                        THEN li.quantity * li.unit_price
                        ELSE 0
                    END
                ),
                CAST(0 AS DECIMAL(38, 4))
            ),
            COALESCE(SUM(li.quantity * li.unit_price), CAST(0 AS DECIMAL(38, 4))),
            COUNT(*)
        FROM line_items AS li
        JOIN customer_facts AS cf ON cf.customer_id = li.customer_id
        WHERE li.order_date BETWEEN ? AND ?
          AND li.order_date >= cf.first_order_date
        """,
        [start, end],
    ).fetchone()
    assert row is not None
    new_sales, returning_sales, identified_sales, identified_rows = row
    return {
        "new_customer_gross_sales": Decimal(new_sales or _ZERO_MONEY),
        "returning_customer_gross_sales": Decimal(returning_sales or _ZERO_MONEY),
        "identified_gross_sales": Decimal(identified_sales or _ZERO_MONEY),
        "identified_rows": int(identified_rows),
    }
