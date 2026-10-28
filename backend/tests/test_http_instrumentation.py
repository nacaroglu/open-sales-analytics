from __future__ import annotations

import asyncio

from app.http_instrumentation import RequestTelemetryMiddleware
from app.telemetry import TelemetryProviders
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _app() -> tuple[FastAPI, InMemorySpanExporter, InMemoryMetricReader]:
    app = FastAPI(
        telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False}
    )
    resource = Resource.create({"service.name": "test"})
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = InMemorySpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    app.state.telemetry = TelemetryProviders(
        resource,
        tracer_provider,
        meter_provider,  # type: ignore[arg-type]
        LoggerProvider(resource=resource),
        False,
    )
    app.add_middleware(RequestTelemetryMiddleware)

    @app.get("/items/{item_id}")
    async def item(item_id: str):
        return {"item": item_id}

    @app.post("/failure")
    async def failure():
        raise HTTPException(status_code=400)

    @app.get("/server-error")
    async def server_error():
        return Response(status_code=503)

    @app.get("/unhandled")
    async def unhandled():
        raise RuntimeError("sensitive exception message")

    return app, span_exporter, metric_reader


def _request(app: FastAPI, path: str, method: str = "GET", headers=(), body=b"") -> int:
    response_status = 500
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = message["status"]

    request_path, separator, query = path.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": request_path,
        "raw_path": request_path.encode(),
        "query_string": query.encode() if separator else b"",
        "root_path": "",
        "headers": list(headers),
        "server": ("test", 80),
        "client": ("test", 1234),
    }
    try:
        asyncio.run(app(scope, receive, send))
    except RuntimeError:
        # Starlette's ServerErrorMiddleware sends a 500 response, then re-raises.
        pass
    return response_status


def test_server_spans_use_route_templates_and_never_capture_request_data() -> None:
    app, exporter, _ = _app()
    response_status = _request(
        app,
        "/items/customer-secret?token=query-secret",
        headers=[(b"authorization", b"Bearer auth-secret")],
    )
    assert response_status == 200

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "GET /items/{item_id}"
    assert span.attributes["http.route"] == "/items/{item_id}"
    rendered = repr((span.name, span.attributes, span.events))
    for secret in ("customer-secret", "query-secret", "auth-secret"):
        assert secret not in rendered


def test_status_class_metrics_and_error_classification_are_bounded() -> None:
    app, exporter, reader = _app()
    assert _request(app, "/items/one") == 200
    assert _request(app, "/failure", method="POST", body=b'{"private":"body-secret"}') == 400
    assert _request(app, "/server-error") == 503
    assert _request(app, "/unhandled") == 500
    assert _request(app, "/missing/raw-secret?token=query-secret") == 404

    spans = exporter.get_finished_spans()
    assert [span.attributes["osa.error.class"] for span in spans] == [
        "none",
        "client_error",
        "server_error",
        "server_error",
        "client_error",
    ]
    assert spans[2].status.status_code.name == "ERROR"
    assert spans[3].status.status_code.name == "ERROR"
    assert not any(event.name == "exception" for span in spans for event in span.events)
    metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
    by_name = {metric.name: metric for metric in metrics}
    request = by_name["http.server.request.count"].data.data_points
    assert sum(point.value for point in request) == 5
    assert {point.attributes["http.response.status_class"] for point in request} == {
        "2xx",
        "4xx",
        "5xx",
    }
    assert all("http.route" in point.attributes for point in request)
    duration_points = by_name["http.server.request.duration"].data.data_points
    assert sum(point.count for point in duration_points) == 5
    assert all(point.sum >= 0 for point in duration_points)
    active = by_name["http.server.active_requests"].data.data_points
    assert all(point.value == 0 for point in active)
    rendered = repr((metrics, spans))
    for secret in (
        "body-secret",
        "raw-secret",
        "query-secret",
        "sensitive exception message",
    ):
        assert secret not in rendered


def test_w3c_trace_parent_is_extracted_and_exporter_unset_path_is_safe() -> None:
    app, exporter, _ = _app()
    trace_id = "1234567890abcdef1234567890abcdef"
    parent_id = "1234567890abcdef"
    assert (
        _request(
            app,
            "/items/one",
            headers=[(b"traceparent", f"00-{trace_id}-{parent_id}-01".encode())],
        )
        == 200
    )
    span = exporter.get_finished_spans()[0]
    assert f"{span.context.trace_id:032x}" == trace_id
    assert f"{span.parent.span_id:016x}" == parent_id

    no_telemetry = FastAPI(
        telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False}
    )
    no_telemetry.add_middleware(RequestTelemetryMiddleware)

    @no_telemetry.get("/ok")
    async def ok():
        return {"ok": True}

    assert _request(no_telemetry, "/ok") == 200
