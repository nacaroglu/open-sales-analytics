"""Application OpenTelemetry providers and bounded resource identity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

from app.config import Settings
from app.custom_metrics import CustomMetrics

_OTLP_PROTOCOL = "http/protobuf"
_GENERIC_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
_SIGNAL_ENDPOINTS = {
    "traces": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "metrics": "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "logs": "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
}


def create_resource(settings: Settings) -> Resource:
    """Return only the bounded application identity attributes used by every signal."""
    return Resource(
        attributes={
            "service.name": "open-sales-analytics",
            "service.namespace": "osa",
            "service.version": settings.osa_version,
            "deployment.environment.name": settings.osa_environment,
        }
    )


def _validated_endpoint(value: str, variable: str) -> str:
    endpoint = value.strip()
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{variable} must be an absolute HTTP(S) URL")
    return endpoint


def _signal_endpoint(signal: str, environ: Mapping[str, str]) -> str | None:
    specific_name = _SIGNAL_ENDPOINTS[signal]
    specific = environ.get(specific_name, "").strip()
    if specific:
        return _validated_endpoint(specific, specific_name)

    generic = environ.get(_GENERIC_ENDPOINT, "").strip()
    if not generic:
        return None

    base = _validated_endpoint(generic, _GENERIC_ENDPOINT).rstrip("/")
    return f"{base}/v1/{signal}"


def _endpoint_configuration(
    environ: Mapping[str, str],
) -> dict[str, str]:
    endpoints = {signal: _signal_endpoint(signal, environ) for signal in _SIGNAL_ENDPOINTS}
    configured = {signal: endpoint for signal, endpoint in endpoints.items() if endpoint}
    if not configured:
        return {}

    protocol = environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", _OTLP_PROTOCOL).strip().lower()
    if protocol != _OTLP_PROTOCOL:
        raise ValueError(
            "OTEL_EXPORTER_OTLP_PROTOCOL must be 'http/protobuf' when an OTLP endpoint is set"
        )
    return configured


@dataclass
class TelemetryProviders:
    """Providers owned by one application lifespan or telemetry test process."""

    resource: Resource
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider
    export_enabled: bool
    custom_metrics: CustomMetrics | None = None

    def emit_synthetic_resource_identity_signal(self) -> None:
        """Emit one fixed trace, metric, and log record without user-derived values."""
        tracer = self.tracer_provider.get_tracer("app.telemetry")
        with tracer.start_as_current_span("osa.synthetic.resource_identity"):
            meter = self.meter_provider.get_meter("app.telemetry")
            counter = meter.create_counter("osa.synthetic.resource_identity")
            counter.add(1, {"signal": "resource_identity_test"})

            logger = self.logger_provider.get_logger("app.telemetry")
            logger.emit(
                LogRecord(
                    body="osa.synthetic.resource_identity",
                    severity_number=SeverityNumber.INFO,
                    severity_text="INFO",
                    event_name="osa.synthetic.resource_identity",
                    attributes={"signal": "resource_identity_test"},
                )
            )

    def force_flush(self, timeout_millis: int = 5_000) -> bool:
        """Flush all signal providers within a bounded timeout."""
        results = (
            self.tracer_provider.force_flush(timeout_millis),
            self.meter_provider.force_flush(timeout_millis),
            self.logger_provider.force_flush(timeout_millis),
        )
        return all(results)

    def shutdown(self) -> None:
        """Flush and close every provider, even if one provider reports an error."""
        shutdown_errors: list[Exception] = []
        for provider in (
            self.logger_provider,
            self.meter_provider,
            self.tracer_provider,
        ):
            try:
                provider.shutdown()
            except Exception as exc:
                shutdown_errors.append(exc)
        if shutdown_errors:
            raise RuntimeError("One or more OpenTelemetry providers failed to shut down") from (
                shutdown_errors[0]
            )


def create_telemetry(
    settings: Settings, environ: Mapping[str, str] | None = None
) -> TelemetryProviders:
    """Create providers with one identity resource and optional OTLP/HTTP exporters.

    With no generic or per-signal OTLP endpoint, providers retain the same resource but
    have no exporter. This keeps local startup independent of an observability backend.
    """
    environment = (
        environ
        if environ is not None
        else {
            name: value
            for name, value in {
                _GENERIC_ENDPOINT: settings.otel_exporter_otlp_endpoint,
                "OTEL_EXPORTER_OTLP_PROTOCOL": settings.otel_exporter_otlp_protocol,
                _SIGNAL_ENDPOINTS["traces"]: settings.otel_exporter_otlp_traces_endpoint,
                _SIGNAL_ENDPOINTS["metrics"]: settings.otel_exporter_otlp_metrics_endpoint,
                _SIGNAL_ENDPOINTS["logs"]: settings.otel_exporter_otlp_logs_endpoint,
            }.items()
            if value is not None
        }
    )
    endpoints = _endpoint_configuration(environment)
    token_file = environment.get("OSA_OTLP_TOKEN_FILE") or settings.otel_token_file
    headers: dict[str, str] = {}
    if endpoints:
        if not token_file:
            raise ValueError("OSA_OTLP_TOKEN_FILE is required when an OTLP endpoint is set")
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise ValueError(
                "Unable to read the configured OTLP authentication token file"
            ) from None
        token_characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        if (
            not token
            or not token.isascii()
            or any(character not in token_characters for character in token)
        ):
            raise ValueError("The configured OTLP authentication token file is empty or invalid")
        headers = {"Authorization": f"Bearer {token}"}
    resource = create_resource(settings)

    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBasedTraceIdRatio(settings.osa_trace_sampling_ratio),
        shutdown_on_exit=False,
    )
    meter_readers = []
    logger_provider = LoggerProvider(resource=resource, shutdown_on_exit=False)

    trace_endpoint = endpoints.get("traces")
    if trace_endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=trace_endpoint, headers=headers))
        )

    metric_endpoint = endpoints.get("metrics")
    if metric_endpoint:
        meter_readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=metric_endpoint, headers=headers)
            )
        )

    log_endpoint = endpoints.get("logs")
    if log_endpoint:
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=log_endpoint, headers=headers))
        )

    meter_provider = MeterProvider(
        resource=resource, metric_readers=meter_readers, shutdown_on_exit=False
    )
    custom_metrics = CustomMetrics(meter_provider, settings)
    return TelemetryProviders(
        resource=resource,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        custom_metrics=custom_metrics,
        export_enabled=bool(endpoints),
    )
