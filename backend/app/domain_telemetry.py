"""Bounded manual spans for dataset and analytics operations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, TracerProvider

from app.custom_metrics import current_metrics

_active_tracer_provider: ContextVar[TracerProvider | None] = ContextVar(
    "osa_active_tracer_provider", default=None
)
P = ParamSpec("P")
R = TypeVar("R")


@contextmanager
def use_tracer_provider(provider: TracerProvider) -> Iterator[None]:
    """Make an application-owned provider available to nested domain operations."""
    token: Token[TracerProvider | None] = _active_tracer_provider.set(provider)
    try:
        yield
    finally:
        _active_tracer_provider.reset(token)


def _tracer(name: str) -> trace.Tracer:
    provider = _active_tracer_provider.get()
    return provider.get_tracer(name) if provider is not None else trace.get_tracer(name)


def _error_code(error: BaseException) -> str:
    if isinstance(error, (TimeoutError, ConnectionError)):
        return "dependency_error"
    if isinstance(error, OSError):
        return "storage_error"
    if isinstance(error, ValueError):
        return "invalid_input"
    return "operation_error"


@contextmanager
def operation_span(
    name: str,
    *,
    module: str,
    source: str | None = None,
) -> Iterator[Span]:
    """Record only fixed operation metadata and a bounded success/failure category."""
    attributes = {"osa.module": module, "osa.operation.outcome": "success"}
    if source is not None:
        attributes["osa.source"] = source
    with _tracer("osa.domain").start_as_current_span(
        name,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except BaseException as exc:
            span.set_attribute("osa.operation.outcome", "failure")
            span.set_attribute("osa.error.code", _error_code(exc))
            span.set_status(Status(StatusCode.ERROR))
            raise


def instrument_operation(
    name: str,
    *,
    module: str,
    source: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a synchronous operation without changing its public signature."""

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            started = perf_counter()
            try:
                with operation_span(name, module=module, source=source):
                    result = function(*args, **kwargs)
            except BaseException:
                metrics = current_metrics()
                if metrics is not None:
                    _record_metric_operation(
                        metrics, name, module, kwargs, "failure", perf_counter() - started
                    )
                raise
            metrics = current_metrics()
            if metrics is not None:
                _record_metric_operation(
                    metrics, name, module, kwargs, "success", perf_counter() - started
                )
            return result

        return wrapped

    return decorate


def _record_metric_operation(metrics, name, module, kwargs, outcome, elapsed) -> None:
    if module == "duckdb":
        operation = "canonical_import" if name.endswith("canonical_import") else "open_dataset"
        metrics.record_duckdb(operation, outcome, elapsed)
        if operation == "canonical_import":
            failure_class = "none" if outcome == "success" else "internal"
            metrics.record_dataset_operation(
                "import",
                kwargs.get("source", "upload"),
                outcome,
                failure_class=failure_class,
                duration_seconds=elapsed,
            )
    elif module in {"overview", "customers", "products"}:
        metrics.record_duckdb("analytics_query", outcome, elapsed)
