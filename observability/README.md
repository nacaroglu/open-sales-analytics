# Local observability stack

This is a standalone Docker Compose project. It does not build, start, stop, or
remove the application Compose project. Its five services share this project's
private Docker network and explicitly named data volumes.

Docker Engine and Docker Compose v2 are required. Grafana requires an admin
password from the environment; no credential is stored here:

```sh
read -rsp 'Grafana admin password: ' GRAFANA_ADMIN_PASSWORD
printf '\n'
export GRAFANA_ADMIN_PASSWORD
```

Validate configuration and start the services:

```sh
docker compose -f observability/compose.yaml config --quiet
docker compose -f observability/compose.yaml up --detach
```

Inspect services and logs:

```sh
docker compose -f observability/compose.yaml ps
docker compose -f observability/compose.yaml logs --follow
```

Grafana is at <http://127.0.0.1:3000>, using `GRAFANA_ADMIN_PASSWORD`.
Prometheus, Loki, and Tempo APIs are at `http://127.0.0.1:9090`,
`http://127.0.0.1:3100`, and `http://127.0.0.1:3200` for local diagnosis. All
published ports bind only to loopback. Override them with `OSA_GRAFANA_PORT`,
`OSA_PROMETHEUS_PORT`, `OSA_LOKI_PORT`, `OSA_TEMPO_HTTP_PORT`,
`OSA_OTLP_GRPC_PORT`, and `OSA_OTLP_HTTP_PORT`.

OTLP enters the Collector on host-local ports 4317 (gRPC) and 4318 (HTTP).
Inside the private network, the Collector routes metrics to Prometheus, logs
to Loki, and traces to Tempo using their Compose service names. It exports
application metrics on `collector:8889`; its own detailed telemetry is exposed
on `collector:8888`. Prometheus scrapes both endpoints.

Collector telemetry includes receiver accepted/refused counts, exporter sent
and failed counts, and sending queue size/capacity. Check the `otelcol-internal`
and `osa-application` targets at <http://127.0.0.1:9090/targets>, then inspect
`docker compose -f observability/compose.yaml logs collector` for export
failures. Logs and traces use bounded queues of 512 batches and finite retries.
Overflow drops telemetry rather than blocking application requests. Check
queue pressure and refused/drop metrics when a backend is unavailable.

CI validates the Collector configuration and sends synthetic OTLP metrics,
logs, and traces, then confirms each signal in its backend API. This offline
route check uses synthetic resource identity only.

Grafana provisions three credential-free data sources from
`observability/provisioning/datasources/datasources.yaml`: Prometheus (`osa-prometheus`),
Loki (`osa-loki`), and Tempo (`osa-tempo`). The `OSA Operations` dashboard is
loaded from `observability/dashboards/osa-operations.json` into the OSA folder.
Its Environment filter is limited to `development` and `production`; Deployed
version values are discovered from application telemetry. Application metric
panels, annotations, and their Loki/Tempo drill-down links use both selections.

The dashboard covers release identity and deployment annotations, request
traffic/reliability, dataset creation and cleanup, analytics/DuckDB operations,
runtime capacity, observability storage, and Collector exports. Grafana shows
`No data` when the selected environment/version has no matching samples. Treat
that as missing telemetry or an unavailable scrape/export path, not as a zero
measurement. Start with the dashboard filters and Prometheus targets, then use
the filtered log and trace links to investigate.

CI runs an offline structural validator for the data-source UIDs/endpoints,
dashboard rows and panels, filters, links, and no-data guidance. It does not
require Grafana or an observability backend.

Stop and remove only this project's containers and network:

```sh
docker compose -f observability/compose.yaml down
```

To also delete this project's data:

```sh
docker compose -f observability/compose.yaml down --volumes
```

Images use explicit release versions, configuration files are mounted
read-only, and Compose gives an actionable error if
`GRAFANA_ADMIN_PASSWORD` is missing.
