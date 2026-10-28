from pathlib import Path

import pytest
from app.config import Settings, get_settings
from app.main import app
from app.telemetry import _endpoint_configuration, create_resource, create_telemetry
from fastapi.testclient import TestClient

OTEL_VARIABLES = (
    "OSA_ENVIRONMENT",
    "OSA_VERSION",
    "OSA_OTLP_TOKEN_FILE",
    "DATASET_DIR",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
)


@pytest.fixture(autouse=True)
def clear_otel_environment(monkeypatch):
    for variable in OTEL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resource_uses_development_and_local_defaults():
    resource = create_resource(Settings())

    assert dict(resource.attributes) == {
        "service.name": "open-sales-analytics",
        "service.namespace": "osa",
        "service.version": "local",
        "deployment.environment.name": "development",
    }


def test_resource_uses_explicit_production_identity():
    resource = create_resource(Settings(osa_environment="production", osa_version="ci-release"))

    assert dict(resource.attributes) == {
        "service.name": "open-sales-analytics",
        "service.namespace": "osa",
        "service.version": "ci-release",
        "deployment.environment.name": "production",
    }


def test_resource_uses_test_version_with_supported_development_environment():
    resource = create_resource(
        Settings(osa_environment="development", osa_version="integration-test")
    )

    assert resource.attributes["service.version"] == "integration-test"
    assert resource.attributes["deployment.environment.name"] == "development"


def test_environment_and_version_change_only_their_own_resource_attributes():
    development = create_resource(
        Settings(osa_environment="development", osa_version="integration-test")
    )
    production = create_resource(
        Settings(osa_environment="production", osa_version="integration-test")
    )
    alternate_version = create_resource(
        Settings(osa_environment="development", osa_version="alternate-test")
    )

    development_attributes = dict(development.attributes)
    production_attributes = dict(production.attributes)
    alternate_version_attributes = dict(alternate_version.attributes)
    assert {
        key: value
        for key, value in development_attributes.items()
        if key != "deployment.environment.name"
    } == {
        key: value
        for key, value in production_attributes.items()
        if key != "deployment.environment.name"
    }
    assert production_attributes["deployment.environment.name"] == "production"
    assert {
        key: value for key, value in development_attributes.items() if key != "service.version"
    } == {
        key: value
        for key, value in alternate_version_attributes.items()
        if key != "service.version"
    }
    assert alternate_version_attributes["service.version"] == "alternate-test"


def test_all_signal_providers_share_the_same_resource_without_an_endpoint():
    telemetry = create_telemetry(Settings(), environ={})
    try:
        assert telemetry.export_enabled is False
        assert telemetry.tracer_provider.resource is telemetry.resource
        assert telemetry.meter_provider._sdk_config.resource is telemetry.resource
        assert telemetry.logger_provider.resource is telemetry.resource
        telemetry.emit_synthetic_resource_identity_signal()
        assert telemetry.force_flush()
    finally:
        telemetry.shutdown()


def test_application_lifespan_owns_and_shuts_down_telemetry(monkeypatch, tmp_path):
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("OSA_ENVIRONMENT", "development")
    monkeypatch.setenv("OSA_VERSION", "local")
    get_settings.cache_clear()
    try:
        with TestClient(app):
            telemetry = app.state.telemetry
            assert telemetry.export_enabled is False
            assert telemetry.resource.attributes["service.name"] == "open-sales-analytics"
        assert app.state.telemetry is None
    finally:
        get_settings.cache_clear()


def test_generic_otlp_endpoint_enables_each_signal_endpoint():
    endpoints = _endpoint_configuration(
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        }
    )

    assert endpoints == {
        "traces": "http://collector:4318/v1/traces",
        "metrics": "http://collector:4318/v1/metrics",
        "logs": "http://collector:4318/v1/logs",
    }


def test_signal_specific_otlp_endpoints_only_enable_configured_signals():
    endpoints = _endpoint_configuration(
        {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://collector.example/v1/traces"}
    )

    assert endpoints == {"traces": "https://collector.example/v1/traces"}


def test_otlp_export_is_disabled_without_an_endpoint_even_with_protocol_setting():
    telemetry = create_telemetry(Settings(), environ={"OTEL_EXPORTER_OTLP_PROTOCOL": "grpc"})
    try:
        assert telemetry.export_enabled is False
    finally:
        telemetry.shutdown()


def test_invalid_protocol_with_endpoint_fails_clearly():
    with pytest.raises(ValueError, match="http/protobuf"):
        create_telemetry(
            Settings(),
            environ={
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
            },
        )


def test_otlp_exporters_use_bearer_token_from_private_file(monkeypatch, tmp_path):
    token_file = tmp_path / "otlp-token"
    token_file.write_text("test-token", encoding="utf-8")
    captured = []

    from app import telemetry as telemetry_module

    span_exporter = telemetry_module.OTLPSpanExporter
    metric_exporter = telemetry_module.OTLPMetricExporter
    log_exporter = telemetry_module.OTLPLogExporter

    def capture_exporter(exporter):
        def create(*, endpoint, headers):
            captured.append((endpoint, headers))
            return exporter(endpoint=endpoint, headers=headers)

        return create

    monkeypatch.setattr(telemetry_module, "OTLPSpanExporter", capture_exporter(span_exporter))
    monkeypatch.setattr(telemetry_module, "OTLPMetricExporter", capture_exporter(metric_exporter))
    monkeypatch.setattr(telemetry_module, "OTLPLogExporter", capture_exporter(log_exporter))
    telemetry = create_telemetry(
        Settings(),
        environ={
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
            "OSA_OTLP_TOKEN_FILE": str(token_file),
        },
    )
    try:
        assert len(captured) == 3
        assert all(headers == {"Authorization": "Bearer test-token"} for _, headers in captured)
    finally:
        telemetry.shutdown()


def test_otlp_endpoint_requires_token_file_but_local_no_endpoint_does_not():
    with pytest.raises(ValueError, match="OSA_OTLP_TOKEN_FILE is required"):
        create_telemetry(
            Settings(), environ={"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318"}
        )
    telemetry = create_telemetry(Settings(), environ={})
    try:
        assert telemetry.export_enabled is False
    finally:
        telemetry.shutdown()


def test_otlp_token_file_read_error_does_not_disclose_token(tmp_path):
    with pytest.raises(
        ValueError, match="Unable to read the configured OTLP authentication token file"
    ):
        create_telemetry(
            Settings(),
            environ={
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
                "OSA_OTLP_TOKEN_FILE": str(tmp_path / "missing-token"),
            },
        )


def test_otlp_token_file_invalid_encoding_does_not_disclose_contents(tmp_path):
    token_file = tmp_path / "otlp-token"
    token_file.write_bytes(b"private-token\xff")

    with pytest.raises(
        ValueError, match="Unable to read the configured OTLP authentication token file"
    ) as raised:
        create_telemetry(
            Settings(),
            environ={
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
                "OSA_OTLP_TOKEN_FILE": str(token_file),
            },
        )

    assert raised.value.__suppress_context__
    assert "private-token" not in str(raised.value)


def test_request_succeeds_when_span_export_fails(monkeypatch, tmp_path):
    import asyncio

    from app import telemetry as telemetry_module
    from app.http_instrumentation import RequestTelemetryMiddleware
    from app.logging_config import RequestLogMiddleware
    from app.main import app
    from opentelemetry.sdk.trace.export import SpanExportResult

    class FailingExporter:
        def __init__(self):
            self.export_calls = 0

        def export(self, spans):
            self.export_calls += 1
            return SpanExportResult.FAILURE

        def shutdown(self):
            pass

        def force_flush(self, timeout_millis=30000):
            return True

    failing_exporter = FailingExporter()
    monkeypatch.setattr(telemetry_module, "OTLPSpanExporter", lambda **kwargs: failing_exporter)
    token_file = tmp_path / "otlp-token"
    token_file.write_text("test-token", encoding="utf-8")
    telemetry = create_telemetry(
        Settings(),
        environ={
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://collector:4318/v1/traces",
            "OSA_OTLP_TOKEN_FILE": str(token_file),
        },
    )
    missing = object()
    previous = getattr(app.state, "telemetry", missing)
    app.state.telemetry = telemetry
    messages = []

    async def handle_request(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"status":"ok"}', "more_body": False})

    async def receive():
        raise AssertionError("the health request does not need to read a request body")

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/health",
        "raw_path": b"/api/health",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
        "state": {},
        "app": app,
    }
    try:
        # The request completes before the batch processor is flushed; export is asynchronous.
        request_app = RequestTelemetryMiddleware(RequestLogMiddleware(handle_request))
        asyncio.run(request_app(scope, receive, send))
        response = next(message for message in messages if message["type"] == "http.response.start")
        body = next(
            message["body"] for message in messages if message["type"] == "http.response.body"
        )
        assert response["status"] == 200
        assert body == b'{"status":"ok"}'
        assert telemetry.force_flush()
        assert failing_exporter.export_calls > 0
    finally:
        if previous is missing:
            delattr(app.state, "telemetry")
        else:
            app.state.telemetry = previous
        telemetry.shutdown()


def test_cloud_collector_requires_bearer_auth_for_otlp_http():
    root = Path(__file__).resolve().parents[2]
    aws_collector = (root / "observability" / "collector.aws.yaml").read_text(encoding="utf-8")
    local_collector = (root / "observability" / "collector.yaml").read_text(encoding="utf-8")
    aws_compose = (root / "observability" / "compose.aws.yaml").read_text(encoding="utf-8")
    bootstrap = (root / "deploy" / "observability" / "bootstrap.sh").read_text(encoding="utf-8")

    assert "authenticator: bearertokenauth" in aws_collector
    assert aws_collector.count("authenticator: bearertokenauth") == 2
    assert "filename: /run/secrets/otlp-token" in aws_collector
    assert "authenticator: bearertokenauth" not in local_collector
    assert "otel/opentelemetry-collector-contrib:0.161.0" in aws_compose
    assert "collector.aws.yaml:/etc/otelcol-contrib/config.yaml:ro" in aws_compose
    assert "target: otlp-token" in aws_compose
    assert "file: ${OTLP_TOKEN_FILE:?OTLP SecureString is required at runtime}" in aws_compose
    assert 'read_otlp_token /osa/dev/observability/otlp-token > "$otlp_token_temp"' in bootstrap
    assert 'read_otlp_token /osa/prod/observability/otlp-token >> "$otlp_token_temp"' in bootstrap
    assert 'export OTLP_TOKEN_FILE="$otlp_token_file"' in bootstrap
    assert 'chown root:10001 "$otlp_token_temp"' in bootstrap


def test_runtime_iam_is_limited_to_environment_token_paths():
    root = Path(__file__).resolve().parents[2]
    foundation_template = (root / "deploy/cloudformation/osa-foundation.yaml").read_text(
        encoding="utf-8"
    )

    dev_role = foundation_template.split("  DevCaddyAuthEc2InstanceRole:\n", 1)[1].split(
        "  Ec2InstanceRole:\n", 1
    )[0]
    prod_role = foundation_template.split("  Ec2InstanceRole:\n", 1)[1].split(
        "  ObservabilityEc2InstanceRole:\n", 1
    )[0]
    collector_role = foundation_template.split("  ObservabilityEc2InstanceRole:\n", 1)[1].split(
        "\nOutputs:\n", 1
    )[0]

    assert "parameter/osa/dev/observability/otlp-token" in dev_role
    assert "parameter/osa/prod/observability/otlp-token" not in dev_role
    assert "parameter/osa/prod/observability/otlp-token" in prod_role
    assert "parameter/osa/dev/observability/otlp-token" not in prod_role
    for path in ("osa/dev/observability/otlp-token", "osa/prod/observability/otlp-token"):
        assert f"parameter/{path}" in collector_role
    for role in (dev_role, prod_role, collector_role):
        assert "kms:ViaService" in role
        assert "kms:EncryptionContext:PARAMETER_ARN" in role
        assert "kms:ResourceAliases: alias/aws/ssm" in role

    dev_execution_role = foundation_template.split("  DevApplicationExecutionRole:\n", 1)[1].split(
        "  ProdApplicationExecutionRole:\n", 1
    )[0]
    prod_execution_role = foundation_template.split("  ProdApplicationExecutionRole:\n", 1)[
        1
    ].split("  ObservabilityExecutionRole:\n", 1)[0]
    for role in (dev_execution_role, prod_execution_role):
        assert "ec2:AuthorizeSecurityGroupIngress" in role
        assert "ec2:RevokeSecurityGroupIngress" in role
        assert "ec2:ResourceTag/OSAStack: osa-observability" in role


def test_application_egress_allows_https_and_only_private_collector_otlp():
    root = Path(__file__).resolve().parents[2]
    template = (root / "deploy/cloudformation/osa-application.yaml").read_text(encoding="utf-8")
    security_group = template.split("  AppSecurityGroup:\n", 1)[1].split(
        "  CollectorOtlpIngress:\n", 1
    )[0]
    egress = security_group.split("      SecurityGroupEgress:\n", 1)[1]
    rules = egress.split("      Tags:\n", 1)[0]

    assert rules.count("        - Description:") == 2
    assert "FromPort: 443\n          ToPort: 443\n          CidrIp: 0.0.0.0/0" in rules
    assert (
        "FromPort: 4318\n          ToPort: 4318\n          DestinationSecurityGroupId:\n"
        "            Fn::ImportValue: osa-observability-CollectorSecurityGroupId"
    ) in rules
    assert "CidrIp:" not in rules.split("FromPort: 4318", 1)[1]
    assert "FromPort: 4317" not in rules and "IpProtocol: -1" not in rules


@pytest.mark.parametrize(
    "endpoint",
    ["collector:4318", "ftp://collector:4318", "https:///missing-host"],
)
def test_invalid_otlp_endpoint_fails_clearly(endpoint):
    with pytest.raises(ValueError, match=r"absolute HTTP\(S\) URL"):
        create_telemetry(Settings(), environ={"OTEL_EXPORTER_OTLP_ENDPOINT": endpoint})
