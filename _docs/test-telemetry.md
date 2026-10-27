# Test telemetry sink

The test-only Collector lives in `docker-compose.test-telemetry.yaml` and extends the root `docker-compose.yaml`.
It accepts OTLP/gRPC and OTLP/HTTP on the internal Compose network and writes received records as JSON to
`/var/lib/otelcol/osa-telemetry.json`. The test override bind-mounts a writable local output directory at
`/var/lib/otelcol`; the Collector runs as UID 10001. Host-published ports are limited to OTLP/HTTP and health,
both bound to loopback (`127.0.0.1`). No vendor account or external telemetry service is used.

Create an output directory the Collector can write, then start the application and sink:

```sh
mkdir -p ./.osa-test-telemetry
chmod 0777 ./.osa-test-telemetry
export OSA_TEST_TELEMETRY_DIR="$PWD/.osa-test-telemetry"
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml up --build --detach
```

The application receives `OTEL_EXPORTER_OTLP_ENDPOINT=http://telemetry-collector:4318` and
`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` from the test override. Inspect the JSON-lines sink directly:

```sh
cat ./.osa-test-telemetry/osa-telemetry.json
```

Remove the app, Collector, Compose-managed data volume, and captured output with:

```sh
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml down --volumes --remove-orphans
rm -rf ./.osa-test-telemetry
```

The output is local and synthetic. The cleanup command removes both the mounted directory and the service.
CI uses synthetic telemetry only and does not print credentials or production data.

## Application resource identity

The application builds trace, metric, and log providers from one OpenTelemetry `Resource` containing
only these attributes:

- `service.name`: `open-sales-analytics`
- `service.namespace`: `osa`
- `service.version`: `OSA_VERSION` (defaults to `local`)
- `deployment.environment.name`: `OSA_ENVIRONMENT` (defaults to `development`; accepts `development`
  or `production`)

With no `OTEL_EXPORTER_OTLP_ENDPOINT` or per-signal endpoint, providers have no exporters and startup
is independent of a Collector. Set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` when configuring an
endpoint; this is the only supported protocol. The generic endpoint is the Collector base URL; the
application appends `/v1/traces`, `/v1/metrics`, and `/v1/logs`. Signal-specific variables
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, and
`OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` override the generic endpoint for their signals.

Inbound HTTP telemetry uses one application middleware and the lifespan-owned providers. It emits
server spans plus request count, duration, and active request metrics with bounded method, route
template, and status-class attributes. FastAPI's built-in telemetry is disabled for this app to
avoid duplicate spans and its raw URL path/query attributes. Request bodies, headers, tokens,
exception messages, and raw paths are not recorded. W3C `traceparent` and `tracestate` are extracted
for trace parenting; requests continue normally when telemetry providers are not initialized.

Domain spans cover sample dataset creation (`osa.dataset.sample.create`), CSV validation
(`osa.csv.validate`), DuckDB canonical import (`osa.duckdb.canonical_import`), Overview query
(`osa.analytics.overview.query`), Customer query (`osa.analytics.customers.query`), Product query
(`osa.analytics.products.query`), and dataset cleanup (`osa.dataset.cleanup`). Each records a fixed
module, a bounded outcome (`success`, `accepted`, `rejected`, or `failure`), and a fixed source where
applicable. Failures add only a bounded error code and error span status. No dataset, token, filename,
business identifier, query, CSV content, SQL text, exception message, or exception event is recorded.
The request middleware and lifespan install the same scoped provider context, so domain spans remain
children of their request span and scheduled cleanup uses the application-owned provider.

For a fixed synthetic trace, counter, and log from the running app, invoke the private module inside
the app container:

```sh
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml exec -T app \
  env PYTHONPATH=/app/backend python -m app.telemetry_test_signal
```

It prints a fixed success message after all providers flush and always shuts them down. The payload
contains no dataset or user data. The CI `telemetry-resource-identity` job checks the three signal
shapes and all four resource attributes in the local Collector file sink.
