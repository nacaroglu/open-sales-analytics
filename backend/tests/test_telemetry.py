import pytest
from app.config import Settings, get_settings
from app.main import app
from app.telemetry import _endpoint_configuration, create_resource, create_telemetry
from fastapi.testclient import TestClient

OTEL_VARIABLES = (
    "OSA_ENVIRONMENT",
    "OSA_VERSION",
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


@pytest.mark.parametrize(
    "endpoint",
    ["collector:4318", "ftp://collector:4318", "https:///missing-host"],
)
def test_invalid_otlp_endpoint_fails_clearly(endpoint):
    with pytest.raises(ValueError, match=r"absolute HTTP\(S\) URL"):
        create_telemetry(Settings(), environ={"OTEL_EXPORTER_OTLP_ENDPOINT": endpoint})
