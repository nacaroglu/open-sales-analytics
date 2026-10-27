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

The custom dataset, validation, analytics and DuckDB instrument catalogue, including units, semantics and the full
dimension allowlists, is documented in [custom-metrics.md](custom-metrics.md).

Application logs are emitted independently of the OTLP exporter as one-line JSON. Each record includes an ISO UTC
timestamp, severity, event/message, service name, environment and version. A valid active span adds its trace and span
IDs. HTTP request records use the bounded method and matched route template, status and duration; they omit raw paths,
query strings and dataset IDs. Exception messages, request/response bodies, authorization headers, tokens, CSV values,
and customer, order, product and dataset identifiers are excluded. Log extras are restricted to known structured
fields, and unknown fields are discarded.

For a fixed synthetic trace, counter, and log from the running app, invoke the private module inside
the app container:

```sh
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml exec -T app \
  env PYTHONPATH=/app/backend python -m app.telemetry_test_signal
```

It prints a fixed success message after all providers flush and always shuts them down. The payload
contains no dataset or user data. The CI `telemetry-resource-identity` job checks the three signal
shapes and all four resource attributes in the local Collector file sink.

## Trace sampling and telemetry privacy

`OSA_TRACE_SAMPLING_RATIO` configures root trace sampling as a finite number in the inclusive
range `0.0`–`1.0`. It defaults to `1.0` in both supported environments, `OSA_ENVIRONMENT=development`
and `OSA_ENVIRONMENT=production`. The base and deployment Compose files pass this setting to the
app container; the generated EC2 Compose environment also defaults it to `1.0`. For example, set
`OSA_TRACE_SAMPLING_RATIO=0.25` in the Compose environment to sample about one quarter of root traces.
Values that are non-finite or outside the range fail settings validation at startup. Parent-based
sampling preserves an incoming parent trace decision. Sampling applies only to traces; metric and
log providers remain unsampled.

Metric dimensions come from the finite allowlists in `app.custom_metrics` and the bounded HTTP
instrumentation. They exclude dataset, order, product and customer identifiers; bearer tokens;
filenames and file paths; URLs and query strings; exception messages; arbitrary validation text;
commit messages; and raw input. Spans retain approved service/environment/version resource identity,
route templates, and bounded operation/error categories while omitting raw request paths, query
strings, exception messages and exception events. Structured request logs follow the same privacy
boundary and use route templates instead of request paths.

The `test_adversarial_request_values_never_reach_structured_logs` test drives private markers through
request paths, query strings, authorization headers, raw request bodies, and exception text. It reads
the emitted JSON log sink and verifies the markers are absent while the bounded route template and
approved deployment version remain available. The in-memory checks above cover the corresponding
metric dimensions and span attributes/events.

## Controlled creation-failure check

The app image also includes a development-only CLI check that exercises the real CSV ingest
service three times against a temporary storage path engineered to fail at dataset creation.
It emits only bounded OpenTelemetry dimensions and a fixed summary; it does not create an HTTP
route or write into the configured dataset directory. The command refuses to start unless the
container has `OSA_ENVIRONMENT=development` and the explicit confirmation flag is present.

From the repository root, run it inside the app container:

```sh
docker compose exec -T app env OSA_ENVIRONMENT=development PYTHONPATH=/app/backend \
  python -m app.controlled_failure --confirm-controlled-failure
```

Expected output is `Controlled failure check passed: 3 internal dataset-creation failures;
temporary storage cleaned.` A nonzero exit means the expected internal failures did not occur,
telemetry could not be flushed or shut down, the command was interrupted, or temporary storage
could not be removed. The isolated temporary directory is cleaned on every exit path; the check
does not touch persistent datasets. Run it only in a development app container. CI covers its
guards, three service calls, bounded metric dimensions, redacted output, interruption, and cleanup
without starting Docker, a Collector, or external services.
