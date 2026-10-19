from datetime import date

import duckdb
from app.analytics.customers.projection import calculate_projection, read_projected_customer_value
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL


def connection_with_rows(rows):
    connection = duckdb.connect(":memory:")
    connection.execute(LINE_ITEMS_DDL)
    connection.execute(ORDER_FACTS_DDL)
    connection.execute(CUSTOMER_FACTS_DDL)
    connection.executemany(
        "INSERT INTO line_items (order_id, order_date, product_id, product_name, "
        "quantity, unit_price, customer_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.execute(
        "INSERT INTO order_facts SELECT order_id, min(order_date), max(order_date), "
        "count(*), sum(quantity), sum(quantity * unit_price) "
        "FROM line_items GROUP BY order_id"
    )
    connection.execute(
        """
        INSERT INTO customer_facts
        SELECT customer_id, min(order_date), CAST(date_trunc('month', min(order_date)) AS DATE),
               count(*), max(order_date), count(DISTINCT order_id), sum(quantity),
               sum(quantity * unit_price)
        FROM line_items WHERE customer_id IS NOT NULL GROUP BY customer_id
        """
    )
    return connection


def line(order_id, day, price, customer_id):
    return (order_id, day, "p", "P", 1, price, customer_id)


def test_hand_worked_mature_cohort_projection_keeps_zero_observed_months_and_ignores_age_12():
    rows = [
        line("a0", date(2024, 11, 1), "50.00", "A1"),
        line("a0b", date(2024, 11, 1), "50.00", "A2"),
        line("a1", date(2024, 12, 1), "10.00", "A1"),
        line("a1b", date(2024, 12, 1), "10.00", "A2"),
        line("a2", date(2025, 1, 1), "5.00", "A1"),
        line("a2b", date(2025, 1, 1), "5.00", "A2"),
        line("a12", date(2025, 11, 1), "999.00", "A1"),
        line("b0", date(2024, 12, 1), "50.00", "B1"),
        line("b0b", date(2024, 12, 1), "50.00", "B2"),
        line("b0c", date(2024, 12, 1), "50.00", "B3"),
        line("b1", date(2025, 1, 1), "10.00", "B1"),
        line("b1b", date(2025, 1, 1), "10.00", "B2"),
        line("b1c", date(2025, 1, 1), "10.00", "B3"),
        line("c0", date(2025, 11, 1), "20.00", "C1"),
        line("c0b", date(2025, 11, 1), "20.00", "C2"),
        line("c0c", date(2025, 11, 1), "20.00", "C3"),
        line("c0d", date(2025, 11, 1), "20.00", "C4"),
    ]
    connection = connection_with_rows(rows)
    try:
        result = calculate_projection(connection, date(2025, 12, 31))
    finally:
        connection.close()

    assert [(row["cohort_month"], row["total_per_customer"]) for row in result["cohorts"]] == [
        ("2024-11", "65.0000"),
        ("2024-12", "60.0000"),
        ("2025-11", "22.0000"),
    ]
    assert result["cohorts"][2]["projected_per_customer"] == "2.0000"
    assert result["headline"] == {
        "customers": 9,
        "observed_per_customer": "43.3333",
        "projected_per_customer": "0.8889",
        "total_per_customer": "44.2222",
        "contributing_mature_cohorts": 2,
        "data_cutoff": "2025-12-31",
    }


def test_cutoff_month_is_observed_but_not_topped_up():
    connection = connection_with_rows(
        [
            line("a", date(2024, 1, 1), "10.00", "A"),
            line("b", date(2025, 12, 15), "20.00", "B"),
            line("b-later", date(2025, 12, 20), "99.00", "B"),
        ]
    )
    try:
        result = calculate_projection(connection, date(2025, 12, 15))
    finally:
        connection.close()
    december = next(row for row in result["cohorts"] if row["cohort_month"] == "2025-12")
    assert december["observed_age_months"] == 1
    assert december["observed_per_customer"] == "20.0000"
    assert december["projected_per_customer"] == "0.0000"


def test_projection_is_deterministic_and_ignores_unidentified_orders():
    rows = [
        line("a", date(2024, 1, 1), "10.00", "A"),
        line("b", date(2025, 12, 1), "20.00", "B"),
        line("secret", date(2025, 12, 1), "999.00", None),
    ]
    connection = connection_with_rows(rows)
    try:
        first = calculate_projection(connection, date(2025, 12, 31))
        second = calculate_projection(connection, date(2025, 12, 31))
    finally:
        connection.close()
    assert first == second
    assert "999.0000" not in str(first)


def test_public_projection_entry_point_returns_no_value_when_eligibility_fails():
    connection = connection_with_rows([line("a", date(2025, 1, 1), "10.00", "A")])
    try:
        assert read_projected_customer_value(connection, date(2025, 1, 1)) is None
    finally:
        connection.close()
