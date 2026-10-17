"""Tests for the authoritative analytics metric and availability contracts."""

from dataclasses import FrozenInstanceError
from datetime import date

import duckdb
import pytest
from app.analytics.shared.availability import Availability, AvailabilityState
from app.analytics.shared.metrics import METRICS, MetricDefinition, get_metric
from app.schema import create_dataset, open_dataset_readonly


def test_metric_registry_is_nonempty_unique_and_contains_existing_api_kpis():
    keys = list(METRICS)

    assert keys
    assert len(keys) == len(set(keys))
    assert {"gross_sales", "orders", "units_sold", "average_order_value"} <= set(keys)
    assert METRICS["identified_customers"].unit == "count"
    assert METRICS["identified_customers"].denominator is None
    assert all(key == metric.key for key, metric in METRICS.items())


def test_every_metric_has_the_required_nonempty_contract_fields():
    required = ("key", "label", "unit", "formula", "numerator", "time_window", "insufficient_data")

    for metric in METRICS.values():
        assert all(getattr(metric, field).strip() for field in required)
        assert metric.denominator is None or metric.denominator.strip()
        assert metric.unit in {"money", "count", "ratio", "percent", "days", "date"}


def test_api_kpi_keys_are_documented_by_the_registry(tmp_path):
    from app.api.datasets import build_summary

    path = tmp_path / "metrics.duckdb"
    create_dataset(path)
    writer = duckdb.connect(str(path))
    try:
        writer.execute(
            "INSERT INTO line_items (order_id, order_date, product_id, product_name, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
            ["order-1", date(2025, 1, 1), "product-1", "Product", 1, "2.00"],
        )
    finally:
        writer.close()

    connection = open_dataset_readonly(path)
    try:
        summary = build_summary(connection, {"currency": "USD"}, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()

    assert set(summary["kpis"]) == {"gross_sales", "orders", "units_sold", "average_order_value"}
    assert set(summary["kpis"]) <= set(METRICS)


def test_metric_definitions_are_frozen_and_reject_blank_required_fields():
    metric = METRICS["gross_sales"]
    with pytest.raises(FrozenInstanceError):
        metric.label = "Other"
    with pytest.raises(ValueError, match="key must be nonempty"):
        MetricDefinition("", "Label", "money", "formula", "numerator", None, "window", "state")
    with pytest.raises(ValueError, match="unit must be one of"):
        MetricDefinition(
            "key", "Label", "currency", "formula", "numerator", None, "window", "state"
        )


def test_get_metric_returns_the_definition_and_unknown_keys_raise_key_error():
    assert get_metric("gross_sales") is METRICS["gross_sales"]
    with pytest.raises(KeyError):
        get_metric("unknown")


def test_availability_states_have_the_exact_public_values():
    assert [(state.name, state.value) for state in AvailabilityState] == [
        ("AVAILABLE", "available"),
        ("UNAVAILABLE", "unavailable"),
        ("INSUFFICIENT_DATA", "insufficient_data"),
        ("LOW_COVERAGE", "low_coverage"),
        ("ZERO_RESULT", "zero_result"),
    ]


def test_availability_is_frozen_and_enforces_reason_invariants():
    available = Availability(AvailabilityState.AVAILABLE)
    assert available.reason is None
    with pytest.raises(FrozenInstanceError):
        available.reason = "no"
    with pytest.raises(ValueError, match="available state must not have a reason"):
        Availability(AvailabilityState.AVAILABLE, "unexpected")
    with pytest.raises(ValueError, match="non-available states require a nonempty reason"):
        Availability(AvailabilityState.UNAVAILABLE)
    assert (
        Availability(AvailabilityState.ZERO_RESULT, "No orders in range").reason
        == "No orders in range"
    )
