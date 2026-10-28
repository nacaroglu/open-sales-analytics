import tempfile
from pathlib import Path

import pytest
from app.config import Settings
from app.controlled_failure import main
from app.custom_metrics import CustomMetrics
from app.ingest import ingest_csv
from app.telemetry import TelemetryProviders
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

ORDER_MARKER = "ORDER_MARKER_268"
PRODUCT_MARKER = "PRODUCT_MARKER_268"
TOKEN_MARKER = "TOKEN_MARKER_268"


def _telemetry_factory_box():
    state = {}

    def factory(settings):
        resource = Resource.create({"service.name": "controlled-failure-test"})
        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        telemetry = TelemetryProviders(
            resource=resource,
            tracer_provider=TracerProvider(resource=resource, shutdown_on_exit=False),
            meter_provider=meter_provider,
            logger_provider=LoggerProvider(resource=resource, shutdown_on_exit=False),
            export_enabled=False,
            custom_metrics=CustomMetrics(meter_provider, settings),
        )
        state["reader"] = reader
        state["telemetry"] = telemetry
        return telemetry

    return factory, state


def _creation_failure_count(reader):
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "osa.dataset.operations":
                    points = [
                        point
                        for point in metric.data.data_points
                        if point.attributes.get("operation") == "create"
                    ]
                    assert len(points) == 1
                    assert points[0].value == 3
                    assert points[0].attributes == {
                        "operation": "create",
                        "source": "upload",
                        "outcome": "failure",
                        "failure_class": "internal",
                    }
                    return points[0].value
    return 0


def test_controlled_failure_refuses_missing_or_non_development_environment_before_attempts(
    tmp_path, capsys
):
    for environment in (None, "production", "staging", ""):
        attempts = []
        telemetry_calls = []
        environ = {} if environment is None else {"OSA_ENVIRONMENT": environment}
        code = main(
            ["--confirm-controlled-failure"],
            environ=environ,
            settings_factory=lambda: Settings(DATASET_DIR=tmp_path / "persistent"),
            telemetry_factory=lambda _settings, calls=telemetry_calls: calls.append(True),
            service=lambda *_args, calls=attempts, **_kwargs: calls.append(True),
            temp_directory_factory=lambda **_kwargs: pytest.fail("must not create temp storage"),
        )
        assert code != 0
        assert attempts == []
        assert telemetry_calls == []
    assert "production" not in capsys.readouterr().out.lower()


def test_controlled_failure_requires_explicit_confirmation_before_attempts(tmp_path):
    attempts = []
    code = main(
        [],
        environ={"OSA_ENVIRONMENT": "development"},
        settings_factory=lambda: Settings(DATASET_DIR=tmp_path / "persistent"),
        telemetry_factory=lambda _settings: pytest.fail("must check confirmation first"),
        service=lambda *_args, **_kwargs: attempts.append(True),
        temp_directory_factory=lambda **_kwargs: pytest.fail("must not create temp storage"),
    )
    assert code != 0
    assert attempts == []


def test_controlled_failure_runs_three_real_service_attempts_and_cleans_isolated_storage(
    tmp_path, capsys
):
    persistent_dir = tmp_path / "persistent"
    persistent_dir.mkdir()
    marker_file = persistent_dir / "keep.txt"
    marker_file.write_text("PERSISTENT_MARKER", encoding="utf-8")

    def settings_factory():
        return Settings(DATASET_DIR=persistent_dir)

    telemetry_factory, telemetry = _telemetry_factory_box()
    attempts = []
    service = ingest_csv

    def observed_service(*args, **kwargs):
        attempts.append((args[0], kwargs.get("source")))
        return service(*args, **kwargs)

    temp_roots = []
    real_temp_factory = tempfile.TemporaryDirectory

    def temp_factory(**kwargs):
        temporary = real_temp_factory(dir=tmp_path, **kwargs)
        temp_roots.append(Path(temporary.name))
        return temporary

    code = main(
        ["--confirm-controlled-failure"],
        environ={"OSA_ENVIRONMENT": "development"},
        settings_factory=settings_factory,
        telemetry_factory=telemetry_factory,
        service=observed_service,
        temp_directory_factory=temp_factory,
    )

    output = capsys.readouterr().out
    assert code == 0
    assert len(attempts) == 3
    assert all(source == "upload" for _, source in attempts)
    assert _creation_failure_count(telemetry["reader"]) == 3
    assert all(not root.exists() for root in temp_roots)
    assert marker_file.read_text(encoding="utf-8") == "PERSISTENT_MARKER"
    assert sorted(path.name for path in persistent_dir.iterdir()) == ["keep.txt"]
    assert all(marker not in output for marker in (ORDER_MARKER, PRODUCT_MARKER, TOKEN_MARKER))
    assert "3 internal dataset-creation failures" in output


def test_unexpected_service_error_is_redacted_and_still_cleans_temporary_storage(tmp_path, capsys):
    telemetry_factory, _telemetry = _telemetry_factory_box()
    attempts = []

    def unexpected_error(*_args, **_kwargs):
        attempts.append(True)
        raise RuntimeError(f"private failure detail {ORDER_MARKER} {PRODUCT_MARKER} {TOKEN_MARKER}")

    temp_roots = []
    real_temp_factory = tempfile.TemporaryDirectory

    def temp_factory(**kwargs):
        temporary = real_temp_factory(dir=tmp_path, **kwargs)
        temp_roots.append(Path(temporary.name))
        return temporary

    code = main(
        ["--confirm-controlled-failure"],
        environ={"OSA_ENVIRONMENT": "development"},
        settings_factory=lambda: Settings(DATASET_DIR=tmp_path / "persistent"),
        telemetry_factory=telemetry_factory,
        service=unexpected_error,
        temp_directory_factory=temp_factory,
    )
    output = capsys.readouterr().out
    assert code != 0
    assert len(attempts) == 3
    assert all(marker not in output for marker in (ORDER_MARKER, PRODUCT_MARKER, TOKEN_MARKER))
    assert "private failure detail" not in output
    assert all(not root.exists() for root in temp_roots)


def test_controlled_failure_returns_nonzero_when_temporary_storage_cleanup_fails(tmp_path, capsys):
    telemetry_factory, _telemetry = _telemetry_factory_box()
    leaked = tmp_path / "controlled-failure-leak"
    leaked.mkdir()

    class UncleanedTemporaryDirectory:
        name = str(leaked)

        def cleanup(self):
            return None

    try:
        code = main(
            ["--confirm-controlled-failure"],
            environ={"OSA_ENVIRONMENT": "development"},
            settings_factory=lambda: Settings(DATASET_DIR=tmp_path / "persistent"),
            telemetry_factory=telemetry_factory,
            service=lambda *_args, **_kwargs: (_ for _ in ()).throw(NotADirectoryError()),
            temp_directory_factory=lambda **_kwargs: UncleanedTemporaryDirectory(),
        )
        assert code != 0
        assert "cleanup" in capsys.readouterr().out.lower()
        assert not leaked.exists()
    finally:
        import shutil

        shutil.rmtree(leaked, ignore_errors=True)


def test_controlled_failure_cleans_temporary_storage_after_interruption(tmp_path, capsys):
    telemetry_factory, _telemetry = _telemetry_factory_box()
    temp_roots = []
    real_temp_factory = tempfile.TemporaryDirectory

    def temp_factory(**kwargs):
        temporary = real_temp_factory(dir=tmp_path, **kwargs)
        temp_roots.append(Path(temporary.name))
        return temporary

    code = main(
        ["--confirm-controlled-failure"],
        environ={"OSA_ENVIRONMENT": "development"},
        settings_factory=lambda: Settings(DATASET_DIR=tmp_path / "persistent"),
        telemetry_factory=telemetry_factory,
        service=lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
        temp_directory_factory=temp_factory,
    )
    assert code != 0
    assert "interrupted" in capsys.readouterr().out.lower()
    assert all(not root.exists() for root in temp_roots)
