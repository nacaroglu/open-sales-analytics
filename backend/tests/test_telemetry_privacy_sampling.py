from __future__ import annotations

import asyncio

import pytest
from app.config import Settings
from app.custom_metrics import (
    DATASET_OPERATIONS,
    DUCKDB_OPERATIONS,
    FAILURE_CLASSES,
    MODULES,
    OUTCOMES,
    SOURCES,
    VALIDATION_ERROR_CODES,
)
from app.domain_telemetry import operation_span
from app.http_instrumentation import RequestTelemetryMiddleware
from app.telemetry import create_telemetry
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.context import Context
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import Decision, ParentBasedTraceIdRatio


@pytest.mark.parametrize("environment", ["development", "production"])
def test_both_environments_default_to_full_trace_sampling(environment):
    settings = Settings(OSA_ENVIRONMENT=environment)
    assert settings.osa_trace_sampling_ratio == 1.0


@pytest.mark.parametrize(
    "ratio",
    ["nan", "inf", "-inf", "-0.01", "1.01"],
)
def test_trace_sampling_ratio_rejects_nonfinite_and_out_of_range_values(ratio, monkeypatch):
    monkeypatch.setenv("OSA_TRACE_SAMPLING_RATIO", ratio)
    with pytest.raises(ValueError):
        Settings()


def test_trace_sampling_ratio_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("OSA_TRACE_SAMPLING_RATIO", "0.25")
    assert Settings().osa_trace_sampling_ratio == 0.25


@pytest.mark.parametrize("environment", ["development", "production"])
def test_full_sampling_records_representative_traces_in_both_environments(environment):
    telemetry = create_telemetry(
        Settings(OSA_ENVIRONMENT=environment, OSA_TRACE_SAMPLING_RATIO="1.0"), environ={}
    )
    exporter = InMemorySpanExporter()
    telemetry.tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        with telemetry.tracer_provider.get_tracer("sampling-test").start_as_current_span(
            "representative"
        ):
            pass
        assert [span.name for span in exporter.get_finished_spans()] == ["representative"]
    finally:
        telemetry.shutdown()


def test_non_full_sampling_uses_the_configured_ratio_for_root_trace_ids():
    telemetry = create_telemetry(Settings(OSA_TRACE_SAMPLING_RATIO="0.25"), environ={})
    try:
        sampler = telemetry.tracer_provider.sampler
        assert isinstance(sampler, ParentBasedTraceIdRatio)
        assert sampler.should_sample(Context(), 0x0000000000000000, "sampled").decision == (
            Decision.RECORD_AND_SAMPLE
        )
        assert sampler.should_sample(Context(), 0x0000000000000001, "sampled").decision == (
            Decision.RECORD_AND_SAMPLE
        )
        assert sampler.should_sample(Context(), 0x4000000000000000, "not-sampled").decision == (
            Decision.DROP
        )
    finally:
        telemetry.shutdown()


def test_trace_sampling_does_not_sample_metrics_or_logs():
    telemetry = create_telemetry(Settings(OSA_TRACE_SAMPLING_RATIO="0.0"), environ={})
    metric_reader = InMemoryMetricReader()
    log_exporter = InMemoryLogRecordExporter()
    telemetry.meter_provider.add_metric_reader(metric_reader)
    telemetry.logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    span_exporter = InMemorySpanExporter()
    telemetry.tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    try:
        with telemetry.tracer_provider.get_tracer("sampling-test").start_as_current_span("dropped"):
            pass
        telemetry.meter_provider.get_meter("sampling-test").create_counter("sampling_test").add(1)
        telemetry.logger_provider.get_logger("sampling-test").emit(
            LogRecord(
                body="sampling-test-log",
                severity_number=SeverityNumber.INFO,
                severity_text="INFO",
            )
        )
        assert span_exporter.get_finished_spans() == ()
        metrics = metric_reader.get_metrics_data().resource_metrics
        assert any(
            metric.name == "sampling_test"
            for resource_metrics in metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        )
        assert [record.log_record.body for record in log_exporter.get_finished_logs()] == [
            "sampling-test-log"
        ]
    finally:
        telemetry.shutdown()


DATASET_MARKER = "DATASET_MARKER_258"
ORDER_MARKER = "ORDER_MARKER_258"
PRODUCT_MARKER = "PRODUCT_MARKER_258"
CUSTOMER_MARKER = "CUSTOMER_MARKER_258"
TOKEN_MARKER = "TOKEN_MARKER_258"
FILENAME_MARKER = "FILENAME_MARKER_258"
PATH_MARKER = "PATH_MARKER_258"
URL_MARKER = "URL_MARKER_258"
QUERY_MARKER = "QUERY_MARKER_258"
EXCEPTION_MARKER = "EXCEPTION_MARKER_258"
VALIDATION_MARKER = "VALIDATION_MARKER_258"
COMMIT_MESSAGE_MARKER = "COMMIT_MESSAGE_MARKER_258"
DEPLOYED_VERSION = "20261027-173000-83242da"
RAW_MARKER = "RAW_INPUT_MARKER_258"
PRIVATE_MARKERS = (
    DATASET_MARKER,
    ORDER_MARKER,
    PRODUCT_MARKER,
    CUSTOMER_MARKER,
    TOKEN_MARKER,
    FILENAME_MARKER,
    PATH_MARKER,
    URL_MARKER,
    QUERY_MARKER,
    EXCEPTION_MARKER,
    VALIDATION_MARKER,
    COMMIT_MESSAGE_MARKER,
    RAW_MARKER,
)


def _request(app: FastAPI, path: str, *, body: bytes, headers: dict[str, str]) -> int:
    status = 500
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]

    path_only, _, query = path.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path_only,
        "raw_path": path_only.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "server": ("test", 80),
        "client": ("test", 1234),
    }
    asyncio.run(app(scope, receive, send))
    return status


def test_metric_dimensions_and_spans_exclude_adversarial_request_values(request):
    settings = Settings(osa_environment="production", osa_version=DEPLOYED_VERSION)
    telemetry = create_telemetry(settings, environ={})
    span_exporter = InMemorySpanExporter()
    telemetry.tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    telemetry.meter_provider.add_metric_reader(metric_reader)
    request.addfinalizer(telemetry.shutdown)
    assert telemetry.custom_metrics is not None

    app = FastAPI(
        telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False}
    )
    app.state.telemetry = telemetry
    app.add_middleware(RequestTelemetryMiddleware)

    @app.post("/api/datasets/{dataset_id}/analytics/{filename:path}")
    async def adversarial_request(dataset_id: str, request: Request):
        body = (await request.body()).decode()
        telemetry.custom_metrics.record_dataset_operation(
            "create", "upload", "failure", failure_class="internal"
        )
        telemetry.custom_metrics.record_dataset_operation(
            DATASET_MARKER, TOKEN_MARKER, "failure", failure_class=FILENAME_MARKER
        )
        telemetry.custom_metrics.record_analytics(URL_MARKER, QUERY_MARKER, 0.25)
        telemetry.custom_metrics.record_validation_rejection(VALIDATION_MARKER)
        try:
            with operation_span("osa.analytics.products.query", module="products"):
                raise ValueError(
                    " ".join(
                        (
                            dataset_id,
                            body,
                            ORDER_MARKER,
                            PRODUCT_MARKER,
                            CUSTOMER_MARKER,
                            EXCEPTION_MARKER,
                            COMMIT_MESSAGE_MARKER,
                            RAW_MARKER,
                        )
                    )
                )
        except ValueError:
            pass
        return JSONResponse({"status": "rejected"}, status_code=400)

    request_url = (
        f"/api/datasets/{DATASET_MARKER}/analytics/{FILENAME_MARKER}/{PATH_MARKER}"
        f"?next=https%3A%2F%2Fexample.invalid%2F{URL_MARKER}&search={QUERY_MARKER}"
    )
    response_status = _request(
        app,
        request_url,
        body=" ".join(PRIVATE_MARKERS).encode(),
        headers={"Authorization": f"Bearer {TOKEN_MARKER}"},
    )
    assert response_status == 400

    spans = span_exporter.get_finished_spans()
    assert {span.name for span in spans} == {
        "POST /api/datasets/{dataset_id}/analytics/{filename:path}",
        "osa.analytics.products.query",
    }
    request_span = next(span for span in spans if span.kind.name == "SERVER")
    assert request_span.attributes["http.route"] == (
        "/api/datasets/{dataset_id}/analytics/{filename:path}"
    )
    assert request_span.resource.attributes["service.name"] == "open-sales-analytics"
    assert request_span.resource.attributes["service.version"] == DEPLOYED_VERSION
    assert request_span.resource.attributes["deployment.environment.name"] == "production"
    domain_span = next(span for span in spans if span.name == "osa.analytics.products.query")
    assert domain_span.attributes["osa.module"] == "products"
    assert domain_span.attributes["osa.error.code"] == "invalid_input"
    assert not domain_span.events

    metric_data = metric_reader.get_metrics_data()
    assert all(
        resource_metrics.resource.attributes
        == {
            "service.name": "open-sales-analytics",
            "service.namespace": "osa",
            "service.version": DEPLOYED_VERSION,
            "deployment.environment.name": "production",
        }
        for resource_metrics in metric_data.resource_metrics
    )
    metrics = [
        metric
        for resource_metrics in metric_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    ]
    observed_attributes = [
        point.attributes for metric in metrics for point in getattr(metric.data, "data_points", ())
    ]
    assert observed_attributes
    assert any(
        attributes.get("operation") == "create"
        and attributes.get("source") == "upload"
        and attributes.get("outcome") == "failure"
        and attributes.get("failure_class") == "internal"
        for attributes in observed_attributes
    )
    for attributes in observed_attributes:
        assert set(attributes) <= {
            "operation",
            "source",
            "outcome",
            "failure_class",
            "module",
            "error_code",
            "http.request.method",
            "http.route",
            "http.response.status_class",
        }
        if "operation" in attributes:
            assert attributes["operation"] in DATASET_OPERATIONS | DUCKDB_OPERATIONS
        if "source" in attributes:
            assert attributes["source"] in SOURCES
        if "outcome" in attributes:
            assert attributes["outcome"] in OUTCOMES
        if "failure_class" in attributes:
            assert attributes["failure_class"] in FAILURE_CLASSES
        if "module" in attributes:
            assert attributes["module"] in MODULES
        if "error_code" in attributes:
            assert attributes["error_code"] in VALIDATION_ERROR_CODES
        if "http.request.method" in attributes:
            assert attributes["http.request.method"] == "POST"
        if "http.route" in attributes:
            assert attributes["http.route"] == (
                "/api/datasets/{dataset_id}/analytics/{filename:path}"
            )
        if "http.response.status_class" in attributes:
            assert attributes["http.response.status_class"] == "4xx"
    serialized = repr(
        (
            [(span.name, span.attributes, span.events, span.resource.attributes) for span in spans],
            [point for point in observed_attributes],
        )
    )
    assert all(marker not in serialized for marker in PRIVATE_MARKERS)
