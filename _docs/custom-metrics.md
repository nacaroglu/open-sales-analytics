# OSA custom metric catalogue

The application records custom metrics through its existing OpenTelemetry meter provider. They remain available to
an in-memory reader in CI and require no exporter or Collector. Instrument callbacks contain only fixed enums and
numeric measurements; identifiers and user supplied values never become metric attributes.

## Dataset lifecycle

| Instrument | Type and unit | Dimensions | Semantics |
| --- | --- | --- | --- |
| `osa.dataset.operations` | Counter, `{operation}` | `operation`, `source`, `outcome`, `failure_class` | One count for each create, validation, import and cleanup operation result. |
| `osa.dataset.processing.duration` | Histogram, seconds (`s`) | `operation`, `source`, `outcome` | Elapsed validation, creation and import processing time. |
| `osa.dataset.rows` | Histogram, rows (`{row}`) | `source`, `outcome` | Number of rows successfully imported into a dataset. |
| `osa.dataset.active` | Observable gauge, datasets (`{dataset}`) | `source` | Current unexpired dataset file count grouped by its persisted source. It exposes no dataset IDs. |
| `osa.dataset.cleanup.failures` | Counter, `{failure}` | `failure_class` | File or directory cleanup failures. |

## Validation, analytics and DuckDB

| Instrument | Type and unit | Dimensions | Semantics |
| --- | --- | --- | --- |
| `osa.validation.rejections` | Counter, `{rejection}` | `error_code` | Rejected inputs grouped by a fixed validation code. These are product feedback, not operational failures. |
| `osa.analytics.requests` | Counter, `{request}` | `module`, `outcome` | Each Overview, Customer or Product route request, including cache hits. |
| `osa.analytics.duration` | Histogram, seconds (`s`) | `module`, `outcome` | Elapsed request time for those analytics routes. |
| `osa.duckdb.operations` | Counter, `{operation}` | `operation`, `outcome` | Dataset opens, canonical imports and analytics query operations. |
| `osa.duckdb.duration` | Histogram, seconds (`s`) | `operation`, `outcome` | Elapsed time for each bounded DuckDB operation. |

Allowed values are code-defined and tested:

- `source`: `sample`, `upload`.
- `module`: `overview`, `customer`, `product`.
- `operation` for dataset lifecycle: `create`, `validate`, `import`, `cleanup`.
- `operation` for DuckDB: `open_dataset`, `canonical_import`, `analytics_query`.
- `outcome`: `success`, `rejected`, `failure`.
- `failure_class`: `none`, `validation`, `capacity`, `internal`, `storage`, `dependency`.
- `error_code`: `file_too_large`, `empty_file`, `invalid_encoding`, `malformed_csv`, `too_many_rows`,
  `no_data_rows`, `missing_column`, `duplicate_column`, `missing_value`, `invalid_date`, `future_date`,
  `invalid_quantity`, `invalid_price`, `negative_price`, `line_total_too_large`, `malformed_row`, `duplicate_line`,
  `validation_failed`, `invalid_request`.

Only `internal` creation failures are operational failures for the dataset creation alert. Validation rejections use
the `rejected` outcome and `validation` failure class; they do not increment the alert's `failure` series. Metric
recording is best effort and never blocks an application operation. With no OTLP metrics exporter configured, the
provider records locally without attempting network export.
