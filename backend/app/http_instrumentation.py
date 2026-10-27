"""Privacy-safe OpenTelemetry instrumentation for inbound ASGI requests."""

from __future__ import annotations

import time
from typing import Any

from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.datastructures import Headers
from starlette.routing import Match

from app.domain_telemetry import use_tracer_provider

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE"}
_PROPAGATOR = TraceContextTextMapPropagator()


def _route_template(scope: dict[str, Any]) -> str:
    app = scope.get("app")
    router = getattr(app, "router", None)
    for route in getattr(router, "routes", ()):
        try:
            match, _ = route.matches(scope)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if match in (Match.FULL, Match.PARTIAL):
            path = getattr(route, "path", None)
            if isinstance(path, str):
                return path
    return "unmatched"


def _status_class(status_code: int) -> str:
    if status_code >= 500:
        return "5xx"
    if status_code >= 400:
        return "4xx"
    if status_code >= 300:
        return "3xx"
    if status_code >= 200:
        return "2xx"
    return "1xx"


class RequestTelemetryMiddleware:
    """Create one server span and bounded request metrics for each HTTP request."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._instruments: dict[Any, tuple[Any, Any, Any]] = {}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        application = scope.get("app")
        telemetry = getattr(getattr(application, "state", None), "telemetry", None)
        if telemetry is None:
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "OTHER")).upper()
        method = method if method in _METHODS else "OTHER"
        route = _route_template(scope)
        attributes = {"http.request.method": method, "http.route": route}
        tracer = telemetry.tracer_provider.get_tracer("osa.http.server")
        counter, duration, active = self._get_instruments(telemetry)

        # Trace context is extracted only from the two W3C trace-context headers.
        headers = Headers(scope=scope)
        carrier = {}
        for header_name in ("traceparent", "tracestate"):
            value = headers.get(header_name)
            if value:
                carrier[header_name] = value
        parent_context = _PROPAGATOR.extract(carrier)

        status_code = 500
        started = time.perf_counter()
        active.add(1, {"http.route": route})

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                candidate = message.get("status")
                if isinstance(candidate, int):
                    status_code = candidate
            await send(message)

        error: BaseException | None = None
        try:
            with use_tracer_provider(telemetry.tracer_provider):
                with tracer.start_as_current_span(
                    f"{method} {route}",
                    context=parent_context,
                    kind=SpanKind.SERVER,
                    record_exception=False,
                    set_status_on_exception=False,
                ) as span:
                    span.set_attributes(attributes)
                    try:
                        await self.app(scope, receive, wrapped_send)
                    except BaseException as exc:
                        error = exc
                        raise
                    finally:
                        if error is not None:
                            status_code = max(status_code, 500)
                        error_class = (
                            "server_error"
                            if status_code >= 500
                            else ("client_error" if status_code >= 400 else "none")
                        )
                        span.set_attribute("http.response.status_code", status_code)
                        span.set_attribute("osa.error.class", error_class)
                        if error_class == "server_error":
                            span.set_status(Status(StatusCode.ERROR))
        finally:
            elapsed = max(0.0, time.perf_counter() - started)
            metric_attributes = {
                **attributes,
                "http.response.status_class": _status_class(status_code),
            }
            counter.add(1, metric_attributes)
            duration.record(elapsed, metric_attributes)
            active.add(-1, {"http.route": route})

    def _get_instruments(self, telemetry: Any) -> tuple[Any, Any, Any]:
        provider = telemetry.meter_provider
        instruments = self._instruments.get(provider)
        if instruments is None:
            meter = provider.get_meter("osa.http.server")
            instruments = (
                meter.create_counter("http.server.request.count", unit="{request}"),
                meter.create_histogram("http.server.request.duration", unit="s"),
                meter.create_up_down_counter("http.server.active_requests", unit="{request}"),
            )
            self._instruments[provider] = instruments
        return instruments


def configure_trace_context_propagation() -> None:
    """Install W3C trace-context propagation for supported outbound integrations."""
    set_global_textmap(_PROPAGATOR)
