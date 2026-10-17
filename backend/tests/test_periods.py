"""Unit tests for shared reporting and comparison-period calculations."""

import inspect
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from app.analytics.shared import periods
from app.analytics.shared.periods import (
    Change,
    InvalidRange,
    comparison_period,
    compute_change,
    recency_anchor,
    resolve_reporting_range,
)

DATASET_MIN = date(2023, 1, 1)
DATASET_MAX = date(2024, 12, 31)


def test_missing_reporting_bounds_resolve_to_the_full_dataset():
    resolved = resolve_reporting_range(None, None, DATASET_MIN, DATASET_MAX)

    assert resolved.start == DATASET_MIN
    assert resolved.end == DATASET_MAX
    assert resolved.length_days == 731


def test_each_missing_reporting_bound_defaults_independently():
    assert resolve_reporting_range(None, date(2023, 1, 5), DATASET_MIN, DATASET_MAX) == (
        resolve_reporting_range(DATASET_MIN, date(2023, 1, 5), DATASET_MIN, DATASET_MAX)
    )
    assert resolve_reporting_range(date(2024, 12, 28), None, DATASET_MIN, DATASET_MAX) == (
        resolve_reporting_range(date(2024, 12, 28), DATASET_MAX, DATASET_MIN, DATASET_MAX)
    )


def test_one_day_and_dataset_edge_reporting_ranges_are_accepted():
    assert (
        resolve_reporting_range(DATASET_MIN, DATASET_MIN, DATASET_MIN, DATASET_MAX).length_days == 1
    )
    assert (
        resolve_reporting_range(DATASET_MIN, date(2023, 1, 2), DATASET_MIN, DATASET_MAX).start
        == DATASET_MIN
    )
    assert (
        resolve_reporting_range(date(2024, 12, 30), DATASET_MAX, DATASET_MIN, DATASET_MAX).end
        == DATASET_MAX
    )


def test_reporting_range_rejects_a_start_after_its_end():
    with pytest.raises(InvalidRange, match="^start must not be after end\\.$"):
        resolve_reporting_range(date(2023, 1, 2), date(2023, 1, 1), DATASET_MIN, DATASET_MAX)


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2022, 12, 31), date(2023, 1, 1)), (date(2024, 12, 31), date(2025, 1, 1))],
)
def test_reporting_range_rejects_bounds_outside_the_dataset(start, end):
    message = "The range must be within 2023-01-01 and 2024-12-31."

    with pytest.raises(InvalidRange, match=f"^{message}$"):
        resolve_reporting_range(start, end, DATASET_MIN, DATASET_MAX)


def test_previous_period_uses_an_equal_inclusive_length():
    reporting_range = resolve_reporting_range(
        date(2024, 3, 1), date(2024, 3, 31), DATASET_MIN, DATASET_MAX
    )

    period = comparison_period(reporting_range, "previous_period", DATASET_MIN)

    assert period.comparison_start == date(2024, 1, 30)
    assert period.comparison_end == date(2024, 2, 29)
    assert period.available is True
    assert period.unavailable_reason is None


def test_previous_period_handles_a_one_day_range_and_year_boundary():
    one_day = resolve_reporting_range(date(2024, 1, 2), date(2024, 1, 2), DATASET_MIN, DATASET_MAX)
    crossing_year = resolve_reporting_range(
        date(2023, 12, 15), date(2024, 1, 14), DATASET_MIN, DATASET_MAX
    )

    assert comparison_period(one_day, "previous_period", DATASET_MIN).comparison_start == date(
        2024, 1, 1
    )
    period = comparison_period(crossing_year, "previous_period", DATASET_MIN)
    assert (period.comparison_start, period.comparison_end) == (
        date(2023, 11, 14),
        date(2023, 12, 14),
    )


def test_previous_year_moves_both_dates_back_one_calendar_year():
    reporting_range = resolve_reporting_range(
        date(2024, 6, 1), date(2024, 6, 30), DATASET_MIN, DATASET_MAX
    )

    period = comparison_period(reporting_range, "previous_year", DATASET_MIN)

    assert (period.comparison_start, period.comparison_end) == (date(2023, 6, 1), date(2023, 6, 30))


@pytest.mark.parametrize(
    ("start", "end", "expected_start", "expected_end"),
    [
        (date(2024, 2, 29), date(2024, 3, 2), date(2023, 2, 28), date(2023, 3, 2)),
        (date(2024, 2, 1), date(2024, 2, 29), date(2023, 2, 1), date(2023, 2, 28)),
    ],
)
def test_previous_year_maps_leap_day_at_either_range_edge(start, end, expected_start, expected_end):
    reporting_range = resolve_reporting_range(start, end, DATASET_MIN, DATASET_MAX)

    period = comparison_period(reporting_range, "previous_year", DATASET_MIN)

    assert (period.comparison_start, period.comparison_end) == (expected_start, expected_end)


def test_previous_year_allows_a_comparison_that_overlaps_the_current_range():
    reporting_range = resolve_reporting_range(
        date(2023, 1, 1), date(2024, 6, 30), DATASET_MIN, DATASET_MAX
    )

    period = comparison_period(reporting_range, "previous_year", date(2022, 1, 1))

    assert (period.comparison_start, period.comparison_end) == (date(2022, 1, 1), date(2023, 6, 30))
    assert period.available is True


@pytest.mark.parametrize("mode", ["previous_period", "previous_year"])
def test_comparison_is_unavailable_for_the_default_full_dataset_range(mode):
    full_range = resolve_reporting_range(None, None, DATASET_MIN, DATASET_MAX)

    period = comparison_period(full_range, mode, DATASET_MIN)

    assert period.available is False
    assert period.unavailable_reason == (
        f"The comparison needs data from {period.comparison_start}, but the dataset starts on 2023-01-01."
    )


@pytest.mark.parametrize("mode", ["previous_period", "previous_year"])
def test_comparison_is_unavailable_when_the_reporting_range_starts_at_dataset_minimum(mode):
    reporting_range = resolve_reporting_range(
        DATASET_MIN, date(2023, 1, 15), DATASET_MIN, DATASET_MAX
    )

    assert comparison_period(reporting_range, mode, DATASET_MIN).available is False


@pytest.mark.parametrize(
    ("mode", "reporting_start", "reporting_end", "available"),
    [
        ("previous_period", date(2023, 1, 2), date(2023, 1, 2), True),
        ("previous_period", date(2023, 1, 1), date(2023, 1, 1), False),
        ("previous_year", date(2024, 1, 1), date(2024, 1, 1), True),
        ("previous_year", date(2023, 12, 31), date(2023, 12, 31), False),
    ],
)
def test_comparison_availability_is_decided_only_by_its_start_date(
    mode, reporting_start, reporting_end, available
):
    reporting_range = resolve_reporting_range(
        reporting_start, reporting_end, DATASET_MIN, DATASET_MAX
    )

    assert comparison_period(reporting_range, mode, DATASET_MIN).available is available


def test_comparison_inside_dataset_is_available_even_without_sales_rows():
    reporting_range = resolve_reporting_range(
        date(2023, 1, 2), date(2023, 1, 2), DATASET_MIN, DATASET_MAX
    )

    assert comparison_period(reporting_range, "previous_period", DATASET_MIN).available is True


def test_comparison_rejects_an_unsupported_mode():
    reporting_range = resolve_reporting_range(DATASET_MIN, DATASET_MIN, DATASET_MIN, DATASET_MAX)

    with pytest.raises(ValueError):
        comparison_period(reporting_range, "quarterly", DATASET_MIN)


@pytest.mark.parametrize(
    ("current", "comparison", "absolute", "percent"),
    [
        (150, 100, Decimal("50"), Decimal("50.00")),
        (0, 100, Decimal("-100"), Decimal("-100.00")),
        (100, 100, Decimal("0"), Decimal("0.00")),
        (1, 3, Decimal("-2"), Decimal("-66.67")),
        (2, 3, Decimal("-1"), Decimal("-33.33")),
    ],
)
def test_nonzero_baseline_change_is_half_up_rounded_and_comparable(
    current, comparison, absolute, percent
):
    change = compute_change(current, comparison)

    assert change == Change(absolute, percent, "comparable")


@pytest.mark.parametrize("baseline", [0, Decimal("0.0000")])
def test_zero_baseline_and_zero_current_is_no_change(baseline):
    assert compute_change(0, baseline) == Change(Decimal("0"), None, "no_change")


def test_positive_current_with_zero_baseline_uses_the_requested_status():
    assert compute_change(4, 0) == Change(Decimal("4"), None, "no_prior_value")
    assert compute_change(4, Decimal("0.0000"), "new") == Change(Decimal("4"), None, "new")


@pytest.mark.parametrize("value", [-1, Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")])
def test_negative_or_non_finite_change_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        compute_change(value, 0)
    with pytest.raises(ValueError):
        compute_change(0, value)


def test_period_values_are_frozen():
    reporting_range = resolve_reporting_range(DATASET_MIN, DATASET_MIN, DATASET_MIN, DATASET_MAX)

    with pytest.raises(FrozenInstanceError):
        reporting_range.start = DATASET_MAX


def test_recency_anchor_is_the_reporting_range_end_for_historical_data():
    reporting_range = resolve_reporting_range(
        date(2020, 1, 1), date(2020, 6, 30), date(2020, 1, 1), date(2020, 6, 30)
    )

    assert recency_anchor(reporting_range) == date(2020, 6, 30)


def test_period_module_has_no_clock_dependency():
    source = inspect.getsource(periods)

    assert "date.today" not in source
    assert "datetime.now" not in source
    assert "get_now" not in source
