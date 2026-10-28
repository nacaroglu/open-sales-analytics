# Local observability stack

This is a standalone Docker Compose project. It does not build, start, stop, or
remove the application Compose project. The five services share only this
project's private Docker network and explicitly named data volumes.

Docker Engine and Docker Compose v2 are required. Grafana requires an admin
password from the environment; no credential is stored in this directory.
From the repository root, set it for the current shell before running Compose:

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

Inspect the services and logs:

```sh
docker compose -f observability/compose.yaml ps
docker compose -f observability/compose.yaml logs --follow
```

Grafana is available at <http://127.0.0.1:3000>. Its password is the value of
`GRAFANA_ADMIN_PASSWORD`. Host port overrides are available through
`OSA_GRAFANA_PORT`, `OSA_OTLP_GRPC_PORT`, and `OSA_OTLP_HTTP_PORT`; all published
ports bind to `127.0.0.1`. Prometheus, Loki, and Tempo have no host-published
ports and are reachable only on the private Compose network.

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

Grafana also provisions `OSARepeatedDatasetCreationFailures` from
`observability/provisioning/alerting/osa-repeated-dataset-failures.json` in the
`osa-reliability` group. It sums ten-minute increases of internal dataset/sample
creation failures by service, environment, and deployed version. It enters the
pending state at three failures and fires only when the threshold remains true
for five minutes. Validation rejections are excluded. When the query returns no
qualifying series, the rule returns to OK so recovery clears the alert. Offline
fixtures cover below-threshold behavior, rejected-input exclusion, the pending
boundary, firing, and resolution; run them with
`python3 scripts/test_grafana_alert.py`.

CI runs offline checks for data-source UIDs/endpoints, dashboard rows and
panels, filters, links, no-data guidance, and the alert's metric expression and
state transitions. These checks do not require Grafana or an observability
backend.

Stop and remove only this project's containers and network:

```sh
docker compose -f observability/compose.yaml down
```

To also delete this project's named data volumes:

```sh
docker compose -f observability/compose.yaml down --volumes
```

The image tags are explicit release versions. Configuration files are mounted
read-only. Compose fails before startup with an actionable message if
`GRAFANA_ADMIN_PASSWORD` is missing. Until the signal-routing change, the
Collector accepts OTLP and discards it through a no-op exporter so telemetry
does not spill into container logs.
