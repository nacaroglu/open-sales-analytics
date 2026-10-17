"""Tests for the authoritative analytics metric and availability contracts."""

from dataclasses import FrozenInstanceError
from datetime import date

import duckdb
import pytest
from app.analytics.shared.availability import Availability, AvailabilityState
from app.analytics.shared.metrics import METRIC_BY_KEY, METRICS, MetricDefinition
from app.schema import create_dataset, open_dataset_readonly


def test_metric_registry_is_nonempty_unique_and_contains_existing_api_kpis():
    keys = [metric.key for metric in METRICS]

    assert keys
    assert len(keys) == len(set(keys))
    assert {"gross_sales", "orders", "units_sold", "average_order_value"} <= set(keys)
    assert METRIC_BY_KEY.keys() == set(keys)


def test_every_metric_has_the_required_nonempty_contract_fields():
    required = ("key", "label", "unit", "formula", "numerator", "time_window", "insufficient_data")

    for metric in METRICS:
        assert all(getattr(metric, field).strip() for field in required)
        assert metric.denominator is None or metric.denominator.strip()
        assert metric.text is None or metric.text.strip()


def test_api_kpi_keys_are_documented_by_the_registry(tmp_path):
    from app.api.datasets import build_summary

    path = tmp_path / "metrics.duckdb"
    create_dataset(path)
    writer = duckdb.connect(str(path))
    try:
        writer.execute(
            "INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)",
            ["order-1", date(2025, 1, 1), "product-1", "Product", 1, "2.00"],
        )
    finally:
        writer.close()

    connection = open_dataset_readonly(path)
    try:
        summary = build_summary(connection, {"currency": "USD"}, date(2025, 1, 1), date(2025, 1, 1))
    finally:
        connection.close()

    assert set(summary["kpis"]) <= set(METRIC_BY_KEY)


def test_metric_definitions_are_frozen_and_reject_blank_required_fields():
    metric = METRICS[0]
    with pytest.raises(FrozenInstanceError):
        metric.label = "Other"
    with pytest.raises(ValueError, match="key must be nonempty"):
        MetricDefinition("", "Label", "unit", "formula", "numerator", None, None, "window", "state")


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
