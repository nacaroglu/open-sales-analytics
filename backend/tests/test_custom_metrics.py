from app.config import Settings
from app.custom_metrics import CustomMetrics, use_custom_metrics
from app.ingest import CreatedDataset, ingest_csv
from app.schema import create_dataset
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import Gauge, Histogram, InMemoryMetricReader, Sum
from opentelemetry.sdk.resources import Resource


def _metrics(tmp_path):
    reader = InMemoryMetricReader()
    provider = MeterProvider(
        resource=Resource.create({"service.name": "test"}), metric_readers=[reader]
    )
    metrics = CustomMetrics(provider, Settings(DATASET_DIR=tmp_path))
    return metrics, reader, provider


def _values(reader, name):
    data = reader.get_metrics_data()
    return [
        (metric.data, point)
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


def test_metric_catalog_records_counters_histograms_and_bounded_attributes(tmp_path):
    metrics, reader, provider = _metrics(tmp_path)
    try:
        metrics.record_dataset_operation("create", "sample", "success", duration_seconds=0.25)
        metrics.record_dataset_rows("sample", "success", 17)
        metrics.record_dataset_operation(
            "create", "upload", "failure", failure_class="internal", duration_seconds=0.5
        )
        metrics.record_cleanup_failure("storage")
        metrics.record_validation_rejection("invalid_quantity")
        metrics.record_analytics("overview", "success", 0.125)
        metrics.record_analytics("product", "failure", 0.25)
        metrics.record_duckdb("canonical_import", "success", 0.1)

        operations = _values(reader, "osa.dataset.operations")
        assert len(operations) == 2
        assert all(point.value == 1 for _, point in operations)
        assert {tuple(sorted(point.attributes.items())) for _, point in operations} == {
            tuple(
                sorted(
                    {
                        "operation": "create",
                        "source": "sample",
                        "outcome": "success",
                        "failure_class": "none",
                    }.items()
                )
            ),
            tuple(
                sorted(
                    {
                        "operation": "create",
                        "source": "upload",
                        "outcome": "failure",
                        "failure_class": "internal",
                    }.items()
                )
            ),
        }
        dataset_duration = _values(reader, "osa.dataset.processing.duration")
        assert sorted(point.sum for _, point in dataset_duration) == [0.25, 0.5]
        assert all(
            set(point.attributes) == {"operation", "source", "outcome"}
            for _, point in dataset_duration
        )
        assert _values(reader, "osa.dataset.rows")[0][1].sum == 17
        assert _values(reader, "osa.dataset.cleanup.failures")[0][1].value == 1
        assert _values(reader, "osa.validation.rejections")[0][1].value == 1
        assert sorted(point.value for _, point in _values(reader, "osa.analytics.requests")) == [
            1,
            1,
        ]
        assert sorted(point.sum for _, point in _values(reader, "osa.analytics.duration")) == [
            0.125,
            0.25,
        ]
        assert _values(reader, "osa.duckdb.operations")[0][1].value == 1
        assert _values(reader, "osa.duckdb.duration")[0][1].sum == 0.1

        metric_types = {
            metric.name: type(metric.data)
            for resource_metrics in reader.get_metrics_data().resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        }
        assert metric_types == {
            "osa.dataset.operations": Sum,
            "osa.dataset.processing.duration": Histogram,
            "osa.dataset.rows": Histogram,
            "osa.dataset.active": Gauge,
            "osa.dataset.cleanup.failures": Sum,
            "osa.validation.rejections": Sum,
            "osa.analytics.requests": Sum,
            "osa.analytics.duration": Histogram,
            "osa.duckdb.operations": Sum,
            "osa.duckdb.duration": Histogram,
        }
    finally:
        provider.shutdown()


def test_invalid_dimensions_are_discarded_without_recording_user_values(tmp_path):
    metrics, reader, provider = _metrics(tmp_path)
    try:
        metrics.record_dataset_operation(
            "MARKER_OPERATION", "MARKER_SOURCE", "failure", failure_class="MARKER_FAILURE"
        )
        metrics.record_validation_rejection("MARKER_CSV_ERROR")
        metrics.record_analytics("MARKER_MODULE", "failure", 0.1)
        metrics.record_duckdb("MARKER_QUERY", "failure", 0.1)
        data = reader.get_metrics_data()
        serialized = repr(data)
        assert "MARKER_" not in serialized
        assert not any(
            _values(reader, name)
            for name in (
                "osa.dataset.operations",
                "osa.validation.rejections",
                "osa.analytics.requests",
                "osa.duckdb.operations",
            )
        )
    finally:
        provider.shutdown()


def test_active_gauge_aggregates_datasets_by_source_without_identifiers(tmp_path):
    metrics, reader, provider = _metrics(tmp_path)
    try:
        for dataset_id, source in (("A" * 22, "sample"), ("B" * 22, "upload")):
            path = tmp_path / f"{dataset_id}.duckdb"
            create_dataset(path)
            import duckdb

            connection = duckdb.connect(str(path))
            try:
                connection.execute(
                    "INSERT INTO dataset_meta (id, currency, created_at, expires_at, token_hash, row_count, source) "
                    "VALUES (?, 'USD', TIMESTAMPTZ '2026-10-27 00:00:00+00', "
                    "TIMESTAMPTZ '2099-01-01 00:00:00+00', 'hash', 1, ?)",
                    [dataset_id, source],
                )
            finally:
                connection.close()

        points = _values(reader, "osa.dataset.active")
        assert {tuple(sorted(point.attributes.items())): point.value for _, point in points} == {
            (("source", "sample"),): 1,
            (("source", "upload"),): 1,
        }
        assert all(
            "A" * 22 not in repr(point.attributes) and "B" * 22 not in repr(point.attributes)
            for _, point in points
        )
    finally:
        provider.shutdown()


def test_validation_rejection_does_not_record_a_dataset_failure(tmp_path):
    metrics, reader, provider = _metrics(tmp_path)
    try:
        metrics.record_validation_rejection("missing_column")
        assert _values(reader, "osa.validation.rejections")[0][1].value == 1
        assert not _values(reader, "osa.dataset.operations")
    finally:
        provider.shutdown()


def test_ingestion_records_validation_import_rows_and_duckdb_metrics(tmp_path):
    settings = Settings(DATASET_DIR=tmp_path / "datasets")
    metrics, reader, provider = _metrics(settings.dataset_dir)
    source_file = tmp_path / "source.csv"
    source_file.write_text(
        "order_id,order_date,product_id,product_name,quantity,unit_price\n"
        "o1,2025-01-02,p1,Mug,2,19.99\n",
        encoding="utf-8",
    )
    try:
        with use_custom_metrics(metrics):
            result = ingest_csv(source_file, "USD", settings, source="sample")

        assert isinstance(result, CreatedDataset)
        operations = _values(reader, "osa.dataset.operations")
        assert {
            (point.attributes["operation"], point.attributes["source"], point.attributes["outcome"])
            for _, point in operations
        } == {("validate", "sample", "success"), ("import", "sample", "success")}
        rows = _values(reader, "osa.dataset.rows")
        assert len(rows) == 1 and rows[0][1].sum == 1
        assert {point.attributes["source"] for _, point in rows} == {"sample"}
        assert _values(reader, "osa.duckdb.operations")
        assert _values(reader, "osa.dataset.active")
    finally:
        provider.shutdown()
