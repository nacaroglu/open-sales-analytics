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
