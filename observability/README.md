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

## Retention and capacity

Prometheus retains samples for at most seven days and also applies a 10 GB TSDB
size cap. Loki's compactor deletes log data after 168 hours; its ingestion rate
is limited to 4 MB/s with a 6 MB burst, at most 5,000 streams, and a 256 KB
maximum line. Tempo retains blocks for 168 hours, caps compacted blocks at 1 GiB,
limits ingestion to 1 MiB/s with a 2 MiB burst, and rejects traces over 5 MB.
All three use local filesystem storage. There are no object-store, snapshot,
backup, or archive destinations.

On the AWS host, `compose.aws.yaml` binds Prometheus, Loki and Tempo data paths
under `/srv/osa-observability`, which is the attached 100 GB encrypted telemetry
EBS volume. The fixed volume bounds the combined filesystem footprint. Prometheus
can remove older blocks when its TSDB cap is reached. Loki and Tempo reject or
fail telemetry writes when their ingestion limits or available disk are
exhausted; Collector export failures and backend logs make that visible. The
application handles requests independently of telemetry export, so backend
capacity failures do not turn into application request failures. The telemetry
volume and its contents are deleted with the observability stack; no telemetry
is preserved for recovery.

The CI validator checks the checked-in service configs without contacting a
backend. When the #263 deployment files are present, the same check verifies the
`TelemetryVolume` encryption, 100 GB cap, attachment, delete policies, and that
the AWS bootstrap mounts the telemetry data paths on that volume. To check a
template revision before it is included in this branch, run:

```sh
python3 scripts/validate_observability_retention.py \
  --ebs-template /path/to/osa-observability.yaml \
  --bootstrap-script /path/to/bootstrap.sh
```

The time-window test uses deterministic timestamps: data exactly seven days old
remains in the window, and data older than seven days is eligible for deletion.

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
