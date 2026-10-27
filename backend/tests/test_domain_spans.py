from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import app.cleanup as cleanup_module
import app.importer as importer_module
import pytest
from app.api import customers, datasets, overview, products
from app.api.module_common import resolve_periods
from app.auth import AuthorizedDataset
from app.cleanup import sweep
from app.config import Settings
from app.domain_telemetry import use_tracer_provider
from app.http_instrumentation import RequestTelemetryMiddleware
from app.importer import dataset_path
from app.ingest import CreatedDataset, ingest_csv
from app.meta import read_meta
from app.schema import open_dataset_readonly
from app.telemetry import TelemetryProviders
from fastapi import FastAPI
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

NOW = datetime(2026, 10, 1, tzinfo=UTC)
CSV = (
    "order_id,order_date,product_id,product_name,quantity,unit_price\n"
    "order-marker,2026-01-01,product-marker,Marker Product,1,2.00\n"
)


def _providers() -> tuple[TracerProvider, InMemorySpanExporter]:
    resource = Resource.create({"service.name": "test"})
    provider = TracerProvider(resource=resource)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _asgi_request(app: FastAPI, path: str) -> None:
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_: dict) -> None:
        return None

    request_path, separator, query = path.partition("?")
    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": request_path,
                "raw_path": request_path.encode(),
                "query_string": query.encode() if separator else b"",
                "root_path": "",
                "headers": [],
                "server": ("test", 80),
                "client": ("test", 1234),
            },
            receive,
            send,
        )
    )


def test_all_domain_operation_spans_are_bounded_and_child_of_request(tmp_path, monkeypatch) -> None:
    settings = Settings(DATASET_DIR=tmp_path / "data")
    provider, exporter = _providers()
    meter_reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[meter_reader])
    telemetry = TelemetryProviders(Resource.create({}), provider, meters, LoggerProvider(), False)
    app = FastAPI(
        telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False}
    )
    app.state.telemetry = telemetry
    app.add_middleware(RequestTelemetryMiddleware)

    created: CreatedDataset | None = None

    @app.get("/analytics")
    async def analytics():
        nonlocal created
        created = datasets._ingest_sample(settings)
        assert created is not None
        path = dataset_path(settings, created.dataset_id)
        connection = open_dataset_readonly(path)
        try:
            meta = read_meta(connection)
            periods = resolve_periods(
                None,
                None,
                "previous_period",
                datetime.fromisoformat(meta["date_range"]["min"]).date(),
                datetime.fromisoformat(meta["date_range"]["max"]).date(),
            )
            overview.build_overview(connection, meta, periods)
            customers.build_customers(connection, meta, periods)
        finally:
            connection.close()

        monkeypatch.setattr(
            products,
            "cached_json",
            lambda cache, key, now, expires, compute: compute(),
        )
        products.get_products(
            start=None,
            end=None,
            comparison="previous_period",
            dormancy_days="60",
            dataset=AuthorizedDataset(created.dataset_id, created.meta),
            settings=settings,
            now=NOW,
            cache=object(),
        )
        rejected = tmp_path / "invalid.csv"
        rejected.write_text("wrong,header\nprivate-marker\n", encoding="utf-8")
        assert not ingest_csv(rejected, "USD", settings, source="upload").ok
        sweep(settings, NOW)

        def expect_failure(operation):
            with pytest.raises((OSError, RuntimeError, ValueError)):
                operation()

        with monkeypatch.context() as patcher:
            patcher.setattr(
                datasets,
                "ingest_csv",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private-marker")),
            )
            expect_failure(lambda: datasets._ingest_sample(settings))

        missing = tmp_path / "missing.csv"
        expect_failure(lambda: ingest_csv(missing, "USD", settings))

        bad_import = tmp_path / "import-failure.csv"
        bad_import.write_text(CSV, encoding="utf-8")
        with monkeypatch.context() as patcher:
            patcher.setattr(
                importer_module,
                "_copy_rows",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private-marker")),
            )
            expect_failure(lambda: ingest_csv(bad_import, "USD", settings))

        with monkeypatch.context() as patcher:
            patcher.setattr(
                overview,
                "read_kpis",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private-marker")),
            )
            expect_failure(lambda: overview.build_overview(connection, meta, periods))
        with monkeypatch.context() as patcher:
            patcher.setattr(
                customers,
                "read_customer_coverage",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private-marker")),
            )
            expect_failure(lambda: customers.build_customers(connection, meta, periods))
        with monkeypatch.context() as patcher:
            patcher.setattr(
                products,
                "read_product_count",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private-marker")),
            )
            expect_failure(
                lambda: products.get_products(
                    start=None,
                    end=None,
                    comparison="previous_period",
                    dormancy_days="60",
                    dataset=AuthorizedDataset(created.dataset_id, created.meta),
                    settings=settings,
                    now=NOW,
                    cache=object(),
                )
            )
        with monkeypatch.context() as patcher:
            patcher.setattr(
                cleanup_module,
                "_sweep_datasets_dir",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private-marker")),
            )
            expect_failure(lambda: sweep(settings, NOW))
        sweep(settings, NOW)
        return {"ok": True}

    _asgi_request(app, "/analytics?token=query-secret")
    spans = exporter.get_finished_spans()
    spans_by_name: dict[str, list] = {}
    for span in spans:
        spans_by_name.setdefault(span.name, []).append(span)
    expected = {
        "osa.dataset.sample.create",
        "osa.csv.validate",
        "osa.duckdb.canonical_import",
        "osa.analytics.overview.query",
        "osa.analytics.customers.query",
        "osa.analytics.products.query",
        "osa.dataset.cleanup",
    }
    assert expected <= spans_by_name.keys()
    request_span = spans_by_name["GET /analytics"][0]
    spans_by_id = {span.context.span_id: span for span in spans}
    for name in expected:
        for operation in spans_by_name[name]:
            current = operation
            ancestors = set()
            while current.parent is not None:
                ancestors.add(current.parent.span_id)
                current = spans_by_id.get(current.parent.span_id)
                if current is None:
                    break
            assert request_span.context.span_id in ancestors
    for name in expected:
        operation_spans = spans_by_name[name]
        assert {span.status.status_code.name for span in operation_spans} == {"UNSET", "ERROR"}
        for span in operation_spans:
            assert set(span.attributes) <= {
                "osa.module",
                "osa.operation.outcome",
                "osa.source",
                "osa.error.code",
            }
            assert span.attributes["osa.module"] in {
                "dataset",
                "validation",
                "duckdb",
                "overview",
                "customers",
                "products",
                "cleanup",
            }
            assert span.attributes["osa.operation.outcome"] in {
                "success",
                "accepted",
                "rejected",
                "failure",
            }
            if "osa.source" in span.attributes:
                assert span.attributes["osa.source"] in {"sample", "upload"}
            if "osa.error.code" in span.attributes:
                assert span.attributes["osa.error.code"] in {
                    "storage_error",
                    "invalid_input",
                    "dependency_error",
                    "operation_error",
                }
            assert "private-marker" not in repr((span.attributes, span.events))
            assert not span.events
    validation_outcomes = {
        span.attributes["osa.operation.outcome"] for span in spans_by_name["osa.csv.validate"]
    }
    assert {"accepted", "rejected", "failure"} <= validation_outcomes
    rendered_spans = repr([(span.name, span.attributes, span.events) for span in spans])
    for private_value in (
        "private-marker",
        "Marker Product",
        "order-marker",
        "product-marker",
        "query-secret",
        "invalid.csv",
        created.dataset_id,
        created.token,
    ):
        assert private_value not in rendered_spans


@pytest.mark.parametrize(
    ("exception", "expected"),
    [(ValueError("private-marker"), "invalid_input"), (OSError("private-marker"), "storage_error")],
)
def test_operation_span_failure_is_bounded_and_does_not_record_exception(
    exception: Exception, expected: str
) -> None:
    from app.domain_telemetry import operation_span

    provider, exporter = _providers()
    with use_tracer_provider(provider), pytest.raises(type(exception)):
        with operation_span("osa.test.failure", module="dataset", source="upload"):
            raise exception

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
    assert span.attributes["osa.operation.outcome"] == "failure"
    assert span.attributes["osa.error.code"] == expected
    assert not span.events
    assert "private-marker" not in repr((span.attributes, span.events))
