from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.analytics.shared.filters import parse_day
from app.analytics.shared.periods import (
    ComparisonPeriod,
    ReportingRange,
    comparison_period,
    resolve_reporting_range,
)
from app.errors import ApiError


@dataclass(frozen=True)
class ModulePeriods:
    current: ReportingRange
    comparison: ComparisonPeriod


def invalid_range(message: str) -> ApiError:
    return ApiError(400, "invalid_range", message)


def resolve_periods(
    start: str | None,
    end: str | None,
    comparison: str,
    dataset_min: date,
    dataset_max: date,
) -> ModulePeriods:
    try:
        range_start = dataset_min if start is None else parse_day("start", start)
        range_end = dataset_max if end is None else parse_day("end", end)
    except ValueError as exc:
        raise invalid_range(str(exc)) from None
    if range_start > range_end:
        raise invalid_range("start must not be after end.")
    if range_start < dataset_min or range_end > dataset_max:
        raise invalid_range(f"The range must be within {dataset_min} and {dataset_max}.")

    try:
        current = resolve_reporting_range(range_start, range_end, dataset_min, dataset_max)
        period = comparison_period(current, comparison, dataset_min)
    except ValueError:
        raise ApiError(
            400,
            "invalid_request",
            "comparison must be previous_period or previous_year.",
        ) from None
    return ModulePeriods(
        current=current,
        comparison=period,
    )


def money(value: int | Decimal) -> str:
    return f"{Decimal(value):.4f}"


def percent(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def compared(value: int | Decimal, baseline: int | Decimal | None, as_money: bool) -> dict:
    value_out = money(value) if as_money else int(value)
    if baseline is None:
        return {
            "value": value_out,
            "comparison_value": None,
            "absolute_change": None,
            "percent_change": None,
            "change_status": None,
        }
    from app.analytics.shared.periods import compute_change

    change = compute_change(value, baseline)
    return {
        "value": value_out,
        "comparison_value": money(baseline) if as_money else int(baseline),
        "absolute_change": money(change.absolute_change)
        if as_money
        else int(change.absolute_change),
        "percent_change": percent(change.percent_change),
        "change_status": change.status,
    }


def comparison_body(periods: ModulePeriods) -> dict:
    comparison = periods.comparison
    return {
        "mode": comparison.mode,
        "current": {
            "start": comparison.current_start.isoformat(),
            "end": comparison.current_end.isoformat(),
        },
        "comparison": {
            "start": comparison.comparison_start.isoformat(),
            "end": comparison.comparison_end.isoformat(),
        },
        "state": "available" if comparison.available else "unavailable",
        "reason": comparison.unavailable_reason,
    }


def envelope(meta: dict, periods: ModulePeriods, granularity: str) -> dict:
    return {
        "range": {
            "start": periods.current.start.isoformat(),
            "end": periods.current.end.isoformat(),
        },
        "currency": meta["currency"],
        "granularity": granularity,
        "comparison": comparison_body(periods),
    }
