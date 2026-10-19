from datetime import date
from decimal import Decimal

import duckdb
from app.analytics.customers.projection_eligibility import (
    _cohort_horizon_end,
    _display_coverage,
    _history_months,
    evaluate_projection_eligibility,
)
from app.schema import CUSTOMER_FACTS_DDL, LINE_ITEMS_DDL, ORDER_FACTS_DDL


def connection_with_rows(rows, customer_column=True):
    connection = duckdb.connect(":memory:")
    connection.execute(
        LINE_ITEMS_DDL
        if customer_column
        else LINE_ITEMS_DDL.replace(",\n    customer_id  VARCHAR", "")
    )
    connection.execute(ORDER_FACTS_DDL)
    connection.execute(CUSTOMER_FACTS_DDL)
    connection.executemany(
        "INSERT INTO line_items (order_id, order_date, product_id, product_name, "
        "quantity, unit_price, customer_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    ) if customer_column else connection.executemany(
        "INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)",
        [row[:6] for row in rows],
    )
    connection.execute(
        "INSERT INTO order_facts SELECT order_id, min(order_date), max(order_date), "
        "count(*), sum(quantity), sum(quantity * unit_price) "
        "FROM line_items GROUP BY order_id"
    )
    if customer_column:
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


def row(order_id, order_date, customer_id):
    return (order_id, order_date, "p", "Product", 1, "10.00", customer_id)


def test_history_month_boundaries_and_month_end_clamping():
    assert _history_months(date(2024, 1, 1), date(2025, 6, 30)) == 18
    assert _history_months(date(2024, 1, 1), date(2025, 6, 29)) == 17
    assert _history_months(date(2023, 8, 31), date(2025, 2, 27)) == 18
    assert _history_months(date(2023, 8, 31), date(2025, 2, 26)) == 17


def test_mature_cohort_boundary_is_inclusive():
    assert _cohort_horizon_end(date(2024, 1, 1)) == date(2024, 12, 31)
    assert _cohort_horizon_end(date(2024, 1, 1)) <= date(2024, 12, 31)
    assert not _cohort_horizon_end(date(2024, 1, 1)) <= date(2024, 12, 30)


def test_missing_customer_column_is_unavailable_but_history_is_evaluated():
    connection = connection_with_rows(
        [row("o1", date(2024, 1, 1), None), row("o2", date(2025, 6, 30), None)],
        customer_column=False,
    )
    try:
        result = evaluate_projection_eligibility(connection, date(2025, 6, 30))
    finally:
        connection.close()
    assert result["status"] == "unavailable"
    assert result["conditions"][0]["actual"] == 18
    assert result["conditions"][1]["actual"] == 0
    assert result["conditions"][2]["actual"] is None
    assert result["conditions"][3]["actual"] == 0


def test_blank_customer_ids_are_ineligible_with_zero_coverage():
    connection = connection_with_rows(
        [row("o1", date(2024, 1, 1), None), row("o2", date(2025, 6, 30), None)]
    )
    try:
        result = evaluate_projection_eligibility(connection, date(2025, 6, 30))
    finally:
        connection.close()
    assert result["status"] == "ineligible"
    assert result["conditions"][2]["actual"] == "0.0000"


def test_exact_thresholds_make_projection_eligible():
    rows = []
    for index in range(500):
        cohort_month = index % 5 + 1
        customer_id = f"customer-{index}"
        rows.append(row(f"first-{index}", date(2024, cohort_month, 1), customer_id))
        rows.append(row(f"repeat-{index}", date(2025, 6, 30), customer_id))
    connection = connection_with_rows(rows)
    try:
        result = evaluate_projection_eligibility(connection, date(2025, 6, 30))
    finally:
        connection.close()
    assert result["status"] == "eligible"
    assert all(condition["passed"] for condition in result["conditions"])
    assert [condition["actual"] for condition in result["conditions"]] == [18, 500, "1.0000", 5]


def test_coverage_is_truncated_before_display():
    assert _display_coverage(Decimal(69995) / Decimal(100000)) == "0.6999"


def test_coverage_uses_exact_ratio_for_pass_fail():
    rows = [row(f"identified-{index}", date(2024, 1, 1), f"C{index}") for index in range(699)]
    rows.extend(row(f"blank-{index}", date(2024, 1, 1), None) for index in range(301))
    connection = connection_with_rows(rows)
    try:
        result = evaluate_projection_eligibility(connection, date(2025, 6, 30))
    finally:
        connection.close()
    coverage_condition = result["conditions"][2]
    assert coverage_condition["actual"] == "0.6990"
    assert coverage_condition["threshold"] == "0.7000"
    assert coverage_condition["passed"] is False


def test_all_conditions_are_reported_and_cutoff_excludes_later_orders():
    rows = [row("o1", date(2024, 1, 1), "C1"), row("o2", date(2025, 6, 30), "C2")]
    connection = connection_with_rows(rows + [row("future", date(2025, 7, 1), "C3")])
    try:
        result = evaluate_projection_eligibility(connection, date(2025, 6, 30))
    finally:
        connection.close()
    assert result["status"] == "ineligible"
    assert [condition["code"] for condition in result["conditions"]] == [
        "history_months",
        "identified_customers",
        "customer_coverage",
        "mature_cohorts",
    ]
    assert result["conditions"][1]["actual"] == 2
    assert result["conditions"][2]["actual"] == "1.0000"
