"""Inclusive reporting and comparison period calculations.

This module deliberately has no database, HTTP, or clock dependency.  Analytics
modules use its frozen value objects so every metric applies the same date and
zero-baseline rules.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

_PERCENT_STEP = Decimal("0.01")
_VALID_COMPARISON_MODES = {"previous_period", "previous_year"}


class InvalidRange(ValueError):
    """A reporting range is invalid for the dataset being queried."""


@dataclass(frozen=True)
class ReportingRange:
    """An inclusive reporting range resolved against a dataset's bounds."""

    start: date
    end: date
    length_days: int


@dataclass(frozen=True)
class ComparisonPeriod:
    """The exact baseline dates and whether the entire baseline is available."""

    mode: str
    current_start: date
    current_end: date
    comparison_start: date
    comparison_end: date
    available: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class Change:
    """A finite, presentation-ready change between two non-negative values."""

    absolute_change: Decimal
    percent_change: Decimal | None
    status: str


def resolve_reporting_range(
    start: date | None, end: date | None, dataset_min: date, dataset_max: date
) -> ReportingRange:
    """Resolve optional inclusive bounds, rejecting ranges outside the dataset."""
    resolved_start = dataset_min if start is None else start
    resolved_end = dataset_max if end is None else end

    if resolved_start > resolved_end:
        raise InvalidRange("start must not be after end.")
    if resolved_start < dataset_min or resolved_end > dataset_max:
        raise InvalidRange(f"The range must be within {dataset_min} and {dataset_max}.")

    return ReportingRange(
        start=resolved_start,
        end=resolved_end,
        length_days=(resolved_end - resolved_start).days + 1,
    )


def comparison_period(range: ReportingRange, mode: str, dataset_min: date) -> ComparisonPeriod:
    """Return an exact previous-period or previous-year baseline for ``range``.

    A baseline is usable only if its first day is covered by the dataset.  Its
    exact dates are still returned when unavailable, allowing callers to state
    why comparison data cannot be shown.
    """
    if mode not in _VALID_COMPARISON_MODES:
        raise ValueError(f"Unsupported comparison mode: {mode}")

    if mode == "previous_period":
        comparison_end = range.start - timedelta(days=1)
        comparison_start = comparison_end - timedelta(days=range.length_days - 1)
    else:
        comparison_start = _previous_calendar_year(range.start)
        comparison_end = _previous_calendar_year(range.end)

    available = comparison_start >= dataset_min
    unavailable_reason = None
    if not available:
        unavailable_reason = (
            f"The comparison needs data from {comparison_start}, "
            f"but the dataset starts on {dataset_min}."
        )

    return ComparisonPeriod(
        mode=mode,
        current_start=range.start,
        current_end=range.end,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        available=available,
        unavailable_reason=unavailable_reason,
    )


def compute_change(
    current: int | Decimal, comparison: int | Decimal, zero_baseline: str = "no_prior_value"
) -> Change:
    """Calculate a finite change, using a label instead of a zero-baseline percent."""
    current_value = _non_negative_decimal(current)
    comparison_value = _non_negative_decimal(comparison)
    absolute_change = current_value - comparison_value

    if comparison_value == 0:
        if current_value == 0:
            return Change(absolute_change, None, "no_change")
        return Change(absolute_change, None, zero_baseline)

    percent_change = ((absolute_change / comparison_value) * 100).quantize(
        _PERCENT_STEP, rounding=ROUND_HALF_UP
    )
    return Change(absolute_change, percent_change, "comparable")


def recency_anchor(range: ReportingRange) -> date:
    """Anchor recency to the selected reporting end, never to a wall clock."""
    return range.end


def _previous_calendar_year(day: date) -> date:
    """Move a date back one calendar year, mapping leap day to 28 February."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, month=2, day=28)


def _non_negative_decimal(value: int | Decimal) -> Decimal:
    """Convert supported finite values while preserving decimal arithmetic."""
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    else:
        raise ValueError("values must be non-negative int or Decimal")

    if not decimal_value.is_finite() or decimal_value < 0:
        raise ValueError("values must be non-negative int or Decimal")
    return decimal_value
