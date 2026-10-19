from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from starlette.responses import JSONResponse, Response

from app.analytics.shared.filters import parse_day
from app.analytics.shared.periods import (
    ComparisonPeriod,
    ReportingRange,
    comparison_period,
    resolve_reporting_range,
)
from app.errors import ApiError
from app.response_cache import CacheKey, ResponseCache


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


_RATIO_STEP = Decimal("0.0001")


def ratio(value: Decimal) -> float:
    """Serialize a ratio as a JSON number rounded half-up to 4 decimals."""
    return float(value.quantize(_RATIO_STEP, rounding=ROUND_HALF_UP))


def compared_ratio(
    numerator: int,
    denominator: int,
    baseline_numerator: int | None,
    baseline_denominator: int | None,
) -> dict:
    """Compare two ratios using their exact fractions.

    A period with a zero denominator has no ratio, so the change is undefined. A
    ``None`` baseline means the comparison period is unavailable.
    """
    current = None if denominator == 0 else Decimal(numerator) / Decimal(denominator)
    baseline = (
        None
        if baseline_numerator is None or not baseline_denominator
        else Decimal(baseline_numerator) / Decimal(baseline_denominator)
    )
    body: dict = {
        "value": None if current is None else ratio(current),
        "comparison_value": None if baseline is None else ratio(baseline),
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }
    if current is not None and baseline is not None:
        from app.analytics.shared.periods import compute_change

        change = compute_change(current, baseline)
        body["absolute_change"] = ratio(change.absolute_change)
        body["percent_change"] = percent(change.percent_change)
        body["change_status"] = change.status
    return body


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


def cache_key(
    dataset_id: str,
    module: str,
    periods: ModulePeriods,
    options: tuple[tuple[str, str], ...] = (),
) -> CacheKey:
    return (
        dataset_id,
        module,
        periods.current.start,
        periods.current.end,
        periods.comparison.mode,
        tuple(sorted(options)),
    )


def dataset_expiry(meta: dict) -> datetime:
    return datetime.fromisoformat(meta["expires_at"].replace("Z", "+00:00"))


def cached_json(
    cache: ResponseCache,
    key: CacheKey,
    now: datetime,
    dataset_expires_at: datetime,
    compute: Callable[[], dict],
) -> Response:
    cached = cache.get(key, now)
    if cached is not None:
        return Response(
            content=cached,
            status_code=200,
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    response = JSONResponse(compute(), headers={"Cache-Control": "no-store"})
    cache.put(key, bytes(response.body), now, dataset_expires_at)
    return response
