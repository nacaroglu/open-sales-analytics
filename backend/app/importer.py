import os
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.config import Settings
from app.domain_telemetry import instrument_operation
from app.schema import create_dataset

# A blank customer_id takes the order's one non-blank ID; validation has already
# rejected orders with two different IDs, so max() picks that single value.
_INSERT_LINE_ITEMS = """
INSERT INTO ds.line_items
SELECT order_id,
       CAST(order_date AS DATE),
       product_id,
       product_name,
       CAST(quantity AS INTEGER),
       CAST(unit_price AS DECIMAL(18,4)),
       coalesce(customer_id, max(customer_id) OVER (PARTITION BY order_id))
FROM staging
ORDER BY row_number
"""

_INSERT_META = """
WITH order_coverage AS (
    SELECT order_id, bool_or(customer_id IS NOT NULL) AS identified
    FROM ds.line_items
    GROUP BY order_id
)
INSERT INTO ds.dataset_meta
SELECT $id, $currency, $created_at, $expires_at, $token_hash,
       (SELECT count(*) FROM ds.line_items), $has_customer_id,
       count(*) FILTER (WHERE identified),
       count(*) FILTER (WHERE NOT identified),
       count(*)
FROM order_coverage
"""

_INSERT_ORDER_FACTS = """
INSERT INTO ds.order_facts
SELECT order_id,
       min(order_date),
       max(order_date),
       CAST(count(*) AS INTEGER),
       CAST(sum(quantity) AS BIGINT),
       CAST(sum(quantity * unit_price) AS DECIMAL(38,4))
FROM ds.line_items
GROUP BY order_id
"""

_INSERT_PRODUCT_FACTS = """
INSERT INTO ds.product_facts
SELECT product_id,
       min(product_name),
       min(order_date),
       max(order_date),
       CAST(sum(quantity * unit_price) AS DECIMAL(38,4)),
       CAST(sum(quantity) AS BIGINT),
       CAST(count(DISTINCT order_id) AS BIGINT)
FROM ds.line_items
GROUP BY product_id
"""

_INSERT_CUSTOMER_FACTS = """
WITH identified_orders AS (
    SELECT DISTINCT li.customer_id,
           of.order_id,
           of.first_order_date,
           of.last_order_date,
           of.units,
           of.gross_sales
    FROM ds.line_items AS li
    JOIN ds.order_facts AS of ON of.order_id = li.order_id
    WHERE li.customer_id IS NOT NULL
), customer_firsts AS (
    SELECT customer_id, min(first_order_date) AS first_order_date
    FROM identified_orders
    GROUP BY customer_id
)
INSERT INTO ds.customer_facts
SELECT orders.customer_id,
       firsts.first_order_date,
       CAST(date_trunc('month', firsts.first_order_date) AS DATE),
       CAST(count(*) FILTER (WHERE orders.first_order_date = firsts.first_order_date) AS INTEGER),
       max(orders.last_order_date),
       CAST(count(*) AS INTEGER),
       CAST(sum(orders.units) AS BIGINT),
       CAST(sum(orders.gross_sales) AS DECIMAL(38,4))
FROM identified_orders AS orders
JOIN customer_firsts AS firsts USING (customer_id)
GROUP BY orders.customer_id, firsts.first_order_date
"""


def dataset_path(settings: Settings, dataset_id: str) -> Path:
    """The dataset file for an ID; the ID must be a plain file-name stem."""
    if not dataset_id or dataset_id != Path(dataset_id).name or dataset_id.startswith("."):
        raise ValueError("dataset_id must be a plain name, not a path")
    return settings.dataset_dir / f"{dataset_id}.duckdb"


@instrument_operation("osa.duckdb.canonical_import", module="duckdb")
def import_dataset(
    staging: duckdb.DuckDBPyConnection,
    csv_path: str | os.PathLike[str],
    dataset_id: str,
    currency: str,
    token_hash: str,
    settings: Settings,
    now: datetime | None = None,
) -> Path:
    """Turn validated staging tables into ``<DATASET_DIR>/<dataset_id>.duckdb``.

    Assumes validation passed; it does not re-validate. Whatever happens, the
    raw CSV at ``csv_path`` is deleted and the staging connection is closed
    before this returns or raises. On failure no file for this dataset ID is
    left behind. The dataset is built under a temporary name and renamed into
    place, so a partial file never appears under its real name.
    """
    try:
        target = dataset_path(settings, dataset_id)
        if target.exists():
            raise FileExistsError(f"dataset {dataset_id} already exists")

        count_row = staging.execute("SELECT count(*) FROM staging").fetchone()
        assert count_row is not None  # count(*) always returns one row
        (row_count,) = count_row
        if row_count == 0:
            raise ValueError("refusing to import a dataset with no rows")

        created_at = now or datetime.now(UTC)
        if created_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        working = target.with_name(f".{target.name}.importing")
        try:
            create_dataset(working)
            customer_flag = staging.execute("SELECT has_customer_id FROM staging_meta").fetchone()
            assert customer_flag is not None
            _copy_rows(
                staging,
                working,
                dataset_id,
                currency,
                token_hash,
                created_at,
                created_at + settings.dataset_ttl,
                bool(customer_flag[0]),
            )
            working.rename(target)
        except BaseException:
            _remove_with_wal(working)
            raise
        return target
    finally:
        staging.close()
        Path(csv_path).unlink(missing_ok=True)


def _copy_rows(
    staging, working, dataset_id, currency, token_hash, created_at, expires_at, has_customer_id
) -> None:
    staging.execute(f"ATTACH '{_quote(working)}' AS ds")
    try:
        staging.execute("BEGIN")
        staging.execute(_INSERT_LINE_ITEMS)
        staging.execute(_INSERT_ORDER_FACTS)
        staging.execute(_INSERT_PRODUCT_FACTS)
        staging.execute(_INSERT_CUSTOMER_FACTS)
        staging.execute(
            _INSERT_META,
            {
                "id": dataset_id,
                "currency": currency,
                "created_at": created_at,
                "expires_at": expires_at,
                "token_hash": token_hash,
                "has_customer_id": has_customer_id,
            },
        )
        staging.execute("COMMIT")
    except BaseException:
        staging.execute("ROLLBACK")
        raise
    finally:
        staging.execute("DETACH ds")


def _quote(path: Path) -> str:
    return str(path).replace("'", "''")


def _remove_with_wal(path: Path) -> None:
    for candidate in (path, path.with_name(path.name + ".wal")):
        candidate.unlink(missing_ok=True)
