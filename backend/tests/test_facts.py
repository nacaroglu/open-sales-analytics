"""Integration tests for the immutable facts built during dataset import."""

from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
import pytest
from app.config import Settings
from app.importer import import_dataset
from app.schema import open_dataset_readonly
from app.validation import stage_csv

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
CUSTOMER_HEADER = HEADER + ",customer_id"
NOW = datetime(2025, 6, 1, 12, 30, tzinfo=UTC)
TOKEN_HASH = "a" * 64


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=6)


def import_rows(tmp_path, settings, *rows, dataset_id="facts"):
    path = tmp_path / "upload.csv"
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return import_dataset(stage_csv(path), path, dataset_id, "USD", TOKEN_HASH, settings, NOW)


def columns(connection, table):
    return connection.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()


def test_import_creates_exact_order_and_product_facts(settings, tmp_path):
    target = import_rows(
        tmp_path,
        settings,
        "multi,2025-01-02,p1,Mug,2,10.25",
        "multi,2025-01-05,p2,Cup,3,0",
        "single,2025-02-10,p1,Mug,1,5.50",
    )

    connection = open_dataset_readonly(target)
    try:
        assert columns(connection, "order_facts") == [
            ("order_id", "VARCHAR", "NO"),
            ("first_order_date", "DATE", "NO"),
            ("last_order_date", "DATE", "NO"),
            ("line_count", "INTEGER", "NO"),
            ("units", "BIGINT", "NO"),
            ("gross_sales", "DECIMAL(38,4)", "NO"),
        ]
        assert columns(connection, "product_facts") == [
            ("product_id", "VARCHAR", "NO"),
            ("product_name", "VARCHAR", "NO"),
            ("first_sale_date", "DATE", "NO"),
            ("last_sale_date", "DATE", "NO"),
            ("lifetime_gross_sales", "DECIMAL(38,4)", "NO"),
            ("lifetime_units", "BIGINT", "NO"),
            ("lifetime_orders", "BIGINT", "NO"),
        ]
        assert connection.execute("SELECT * FROM order_facts ORDER BY order_id").fetchall() == [
            (
                "multi",
                date(2025, 1, 2),
                date(2025, 1, 5),
                2,
                5,
                Decimal("20.5000"),
            ),
            (
                "single",
                date(2025, 2, 10),
                date(2025, 2, 10),
                1,
                1,
                Decimal("5.5000"),
            ),
        ]
        assert connection.execute("SELECT * FROM product_facts ORDER BY product_id").fetchall() == [
            (
                "p1",
                "Mug",
                date(2025, 1, 2),
                date(2025, 2, 10),
                Decimal("26.0000"),
                3,
                2,
            ),
            (
                "p2",
                "Cup",
                date(2025, 1, 5),
                date(2025, 1, 5),
                Decimal("0.0000"),
                3,
                1,
            ),
        ]
        assert connection.execute(
            "SELECT count(*), count(DISTINCT order_id) FROM line_items"
        ).fetchone() == (3, 2)
        assert connection.execute("SELECT count(*) FROM order_facts").fetchone() == (2,)
        assert connection.execute(
            "SELECT (SELECT sum(units) FROM order_facts), "
            "(SELECT sum(quantity) FROM line_items), "
            "(SELECT sum(gross_sales) FROM order_facts), "
            "(SELECT sum(quantity * unit_price) FROM line_items)"
        ).fetchone() == (6, 6, Decimal("26.0000"), Decimal("26.0000"))
    finally:
        connection.close()


def test_fact_insert_failure_rolls_back_dataset_and_csv(settings, tmp_path, monkeypatch):
    import app.importer as importer

    path = tmp_path / "upload.csv"
    path.write_text(HEADER + "\no1,2025-01-02,p1,Mug,1,1\n", encoding="utf-8")
    monkeypatch.setattr(importer, "_INSERT_PRODUCT_FACTS", "INSERT INTO no_such_table")

    with pytest.raises(duckdb.Error):
        import_dataset(stage_csv(path), path, "failed", "USD", TOKEN_HASH, settings, NOW)

    assert not path.exists()
    assert not list(settings.dataset_dir.glob("failed.duckdb*"))
    assert not list(settings.dataset_dir.glob(".failed.duckdb.importing*"))


def test_customer_facts_use_full_history_distinct_orders_and_decimal_sales(settings, tmp_path):
    path = tmp_path / "upload.csv"
    path.write_text(
        CUSTOMER_HEADER
        + "\n"
        + "o1,2025-01-10,p1,Mug,2,10.25,C1\n"
        + "o2,2025-01-10,p2,Cup,1,0,C1\n"
        + "o3,2025-03-05,p1,Mug,3,1.50,C1\n"
        + "o4,2024-02-29,p3,Hat,1,2.00,C2\n",
        encoding="utf-8",
    )
    target = import_dataset(stage_csv(path), path, "customers", "USD", TOKEN_HASH, settings, NOW)

    connection = open_dataset_readonly(target)
    try:
        assert connection.execute(
            "SELECT * FROM customer_facts ORDER BY customer_id"
        ).fetchall() == [
            (
                "C1",
                date(2025, 1, 10),
                date(2025, 1, 1),
                2,
                date(2025, 3, 5),
                3,
                6,
                Decimal("25.0000"),
            ),
            (
                "C2",
                date(2024, 2, 29),
                date(2024, 2, 1),
                1,
                date(2024, 2, 29),
                1,
                1,
                Decimal("2.0000"),
            ),
        ]
        assert connection.execute(
            "SELECT count(*), sum(lifetime_orders) FROM customer_facts"
        ).fetchone() == (2, 4)
    finally:
        connection.close()


def test_customer_facts_are_empty_for_six_column_upload(settings, tmp_path):
    target = import_rows(tmp_path, settings, "o1,2025-01-02,p1,Mug,1,1")
    connection = open_dataset_readonly(target)
    try:
        assert connection.execute("SELECT count(*) FROM customer_facts").fetchone() == (0,)
    finally:
        connection.close()


def test_customer_facts_are_empty_when_all_customer_ids_are_blank(settings, tmp_path):
    path = tmp_path / "upload.csv"
    path.write_text(CUSTOMER_HEADER + "\no1,2025-01-02,p1,Mug,1,1,\n", encoding="utf-8")
    target = import_dataset(
        stage_csv(path), path, "blank-customers", "USD", TOKEN_HASH, settings, NOW
    )

    connection = open_dataset_readonly(target)
    try:
        assert connection.execute("SELECT count(*) FROM customer_facts").fetchone() == (0,)
    finally:
        connection.close()


def test_customer_facts_do_not_depend_on_reporting_range_or_import_time(settings, tmp_path):
    targets = []
    for dataset_id in ("facts-a", "facts-b"):
        path = tmp_path / f"{dataset_id}.csv"
        path.write_text(CUSTOMER_HEADER + "\no1,2025-01-10,p1,Mug,1,1,C1\n", encoding="utf-8")
        targets.append(
            import_dataset(stage_csv(path), path, dataset_id, "USD", TOKEN_HASH, settings, NOW)
        )
    connections = [open_dataset_readonly(path) for path in targets]
    try:
        rows = [
            connection.execute("SELECT * FROM customer_facts").fetchall()
            for connection in connections
        ]
        assert rows[0] == rows[1]
    finally:
        for connection in connections:
            connection.close()


def test_customer_fact_failure_rolls_back_dataset_and_csv(settings, tmp_path, monkeypatch):
    import app.importer as importer

    path = tmp_path / "upload.csv"
    path.write_text(CUSTOMER_HEADER + "\no1,2025-01-02,p1,Mug,1,1,C1\n", encoding="utf-8")
    monkeypatch.setattr(importer, "_INSERT_CUSTOMER_FACTS", "INSERT INTO no_such_customer_table")

    with pytest.raises(duckdb.Error):
        import_dataset(stage_csv(path), path, "failed-customers", "USD", TOKEN_HASH, settings, NOW)

    assert not path.exists()
    assert not list(settings.dataset_dir.glob("failed-customers.duckdb*"))
    assert not list(settings.dataset_dir.glob(".failed-customers.duckdb.importing*"))
