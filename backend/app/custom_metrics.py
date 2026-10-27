"""Bounded OpenTelemetry metrics for OSA dataset and analytics operations."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

import duckdb
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider

from app.config import Settings

_DATASET_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")

SOURCES = frozenset({"sample", "upload"})
MODULES = frozenset({"overview", "customer", "product"})
OUTCOMES = frozenset({"success", "rejected", "failure"})
FAILURE_CLASSES = frozenset({"none", "validation", "capacity", "internal", "storage", "dependency"})
DATASET_OPERATIONS = frozenset({"create", "validate", "import", "cleanup"})
DUCKDB_OPERATIONS = frozenset({"open_dataset", "canonical_import", "analytics_query"})
VALIDATION_ERROR_CODES = frozenset(
    {
        "file_too_large",
        "empty_file",
        "invalid_encoding",
        "malformed_csv",
        "too_many_rows",
        "no_data_rows",
        "missing_column",
        "duplicate_column",
        "missing_value",
        "invalid_date",
        "future_date",
        "invalid_quantity",
        "invalid_price",
        "negative_price",
        "line_total_too_large",
        "malformed_row",
        "duplicate_line",
        "validation_failed",
        "invalid_request",
    }
)

_current_metrics: ContextVar[CustomMetrics | None] = ContextVar("osa_custom_metrics", default=None)


@contextmanager
def use_custom_metrics(metrics: CustomMetrics):
    """Bind the app-owned metric instruments through async and worker-thread contexts."""
    token: Token[CustomMetrics | None] = _current_metrics.set(metrics)
    try:
        yield
    finally:
        _current_metrics.reset(token)


def current_metrics() -> CustomMetrics | None:
    return _current_metrics.get()


class CustomMetrics:
    """Metric instruments whose dimensions come only from fixed code allowlists."""

    def __init__(self, provider: MeterProvider, settings: Settings) -> None:
        self.dataset_dir = settings.dataset_dir
        meter = provider.get_meter("osa.custom")
        self.dataset_operations = meter.create_counter(
            "osa.dataset.operations",
            unit="{operation}",
            description="Dataset lifecycle operation outcomes",
        )
        self.dataset_duration = meter.create_histogram(
            "osa.dataset.processing.duration", unit="s", description="Dataset processing duration"
        )
        self.dataset_rows = meter.create_histogram(
            "osa.dataset.rows", unit="{row}", description="Rows in processed datasets"
        )
        self.dataset_active = meter.create_observable_gauge(
            "osa.dataset.active",
            callbacks=[self._active_dataset_observations],
            unit="{dataset}",
            description="Current unexpired datasets by source",
        )
        self.cleanup_failures = meter.create_counter(
            "osa.dataset.cleanup.failures", unit="{failure}", description="Dataset cleanup failures"
        )
        self.validation_rejections = meter.create_counter(
            "osa.validation.rejections",
            unit="{rejection}",
            description="Input validation rejections",
        )
        self.analytics_requests = meter.create_counter(
            "osa.analytics.requests", unit="{request}", description="Analytics request outcomes"
        )
        self.analytics_duration = meter.create_histogram(
            "osa.analytics.duration", unit="s", description="Analytics request duration"
        )
        self.duckdb_operations = meter.create_counter(
            "osa.duckdb.operations", unit="{operation}", description="DuckDB operation outcomes"
        )
        self.duckdb_duration = meter.create_histogram(
            "osa.duckdb.duration", unit="s", description="DuckDB operation duration"
        )

    def record_dataset_operation(
        self,
        operation: str,
        source: str,
        outcome: str,
        *,
        failure_class: str = "none",
        duration_seconds: float | None = None,
    ) -> None:
        if operation not in DATASET_OPERATIONS or source not in SOURCES or outcome not in OUTCOMES:
            return
        if failure_class not in FAILURE_CLASSES:
            return
        attrs = {
            "operation": operation,
            "source": source,
            "outcome": outcome,
            "failure_class": failure_class,
        }
        self._record(self.dataset_operations.add, 1, attrs)
        if duration_seconds is not None:
            self._record_duration(
                self.dataset_duration,
                duration_seconds,
                {"operation": operation, "source": source, "outcome": outcome},
            )

    def record_dataset_rows(self, source: str, outcome: str, rows: int) -> None:
        if source not in SOURCES or outcome not in OUTCOMES or rows < 0:
            return
        self._record(self.dataset_rows.record, rows, {"source": source, "outcome": outcome})

    def record_cleanup_failure(self, failure_class: str) -> None:
        if failure_class not in FAILURE_CLASSES - {"none", "validation"}:
            return
        self._record(self.cleanup_failures.add, 1, {"failure_class": failure_class})

    def record_validation_rejection(self, error_code: str) -> None:
        if error_code not in VALIDATION_ERROR_CODES:
            return
        self._record(self.validation_rejections.add, 1, {"error_code": error_code})

    def record_analytics(self, module: str, outcome: str, duration_seconds: float) -> None:
        if module not in MODULES or outcome not in OUTCOMES:
            return
        attrs = {"module": module, "outcome": outcome}
        self._record(self.analytics_requests.add, 1, attrs)
        self._record_duration(self.analytics_duration, duration_seconds, attrs)

    def record_duckdb(self, operation: str, outcome: str, duration_seconds: float) -> None:
        if operation not in DUCKDB_OPERATIONS or outcome not in OUTCOMES:
            return
        attrs = {"operation": operation, "outcome": outcome}
        self._record(self.duckdb_operations.add, 1, attrs)
        self._record_duration(self.duckdb_duration, duration_seconds, attrs)

    def _record_duration(
        self, histogram: Any, duration_seconds: float, attributes: dict[str, str]
    ) -> None:
        if duration_seconds < 0:
            return
        self._record(histogram.record, duration_seconds, attributes)

    @staticmethod
    def _record(record: Any, value: int | float, attributes: dict[str, str]) -> None:
        try:
            record(value, attributes)
        except Exception:
            # A metrics backend is diagnostic; telemetry must never block user work.
            return

    def _active_dataset_observations(self, _options: Any) -> Iterable[Observation]:
        counts: Counter[str] = Counter()
        try:
            paths = self.dataset_dir.glob("*.duckdb")
            for path in paths:
                if _DATASET_ID.fullmatch(path.stem) is None:
                    continue
                try:
                    connection = duckdb.connect(str(path), read_only=True)
                    try:
                        try:
                            row = connection.execute(
                                "SELECT source FROM dataset_meta "
                                "WHERE expires_at > CURRENT_TIMESTAMP LIMIT 1"
                            ).fetchone()
                        except duckdb.Error:
                            row = connection.execute(
                                "SELECT 'upload' FROM dataset_meta "
                                "WHERE expires_at > CURRENT_TIMESTAMP LIMIT 1"
                            ).fetchone()
                    finally:
                        connection.close()
                except (OSError, duckdb.Error):
                    continue
                if row is not None:
                    source = row[0] if row[0] in SOURCES else "upload"
                    counts[source] += 1
        except OSError:
            return []
        return [Observation(counts[source], {"source": source}) for source in sorted(SOURCES)]


def record_validation_rejection(error_code: str) -> None:
    metrics = current_metrics()
    if metrics is not None:
        metrics.record_validation_rejection(error_code)
