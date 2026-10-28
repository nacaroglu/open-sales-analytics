# Grafana tutorial: set up the local stack and use it with OSA

This tutorial starts the local observability stack, sends telemetry from the application to it, and walks through the provisioned Grafana dashboard and alert. Every command, variable and path comes from this repository: [`observability/compose.yaml`](../observability/compose.yaml), [`observability/collector.yaml`](../observability/collector.yaml), [`scripts/start_observability.sh`](../scripts/start_observability.sh), and the application's telemetry settings.

**Verification status.** The configuration rules and the sample-dataset endpoint were checked against the code. The full walkthrough was not run end to end with Docker, and step 7 runs the controlled-failure utility on the host, whereas its existing documentation runs it in the app container. Treat any step that does not behave as written as a documentation bug and fix it here.

For the authenticated AWS setup, token rotation and production verification, see [`observability/README.md`](../observability/README.md) and [`deploy/README.md`](../deploy/README.md). This tutorial covers the local stack only.

## How the pieces fit

```
Application (on the host) --OTLP/HTTP :4318--> Collector --> Prometheus  (metrics)
                                                         |--> Loki        (logs)
                                                         '--> Tempo       (traces)
                                         Grafana reads all three (http://127.0.0.1:3000)
```

The local stack is a standalone Compose project (`osa-observability`) of five services: `collector`, `prometheus`, `loki`, `tempo` and `grafana`. It does not start, stop or modify the application's own Compose project.

## 0. Prerequisites

- Docker Engine and Docker Compose v2. On Windows with WSL, enable the distribution under Docker Desktop, Settings, Resources, WSL integration, then check `docker compose version`.
- `uv` and the repository dependencies (`uv sync`) to run the backend.
- `sudo`, to set the owner of the webhook secret file (step 1).

## 1. Start the stack

**Grafana admin password.** It is read from the environment and is never stored in a file:

```sh
read -rsp 'Grafana admin password: ' GRAFANA_ADMIN_PASSWORD; printf '\n'
export GRAFANA_ADMIN_PASSWORD
```

**Webhook secret file.** The alert is provisioned with a webhook contact point, so Compose requires `OSA_ALERT_WEBHOOK_URL_FILE` even locally. The file must be outside the repository, owned by Grafana's container user (UID 472), mode `0400`, and contain one HTTPS URL with an external hostname. If you have no receiver, a placeholder such as `https://hooks.example.invalid/local` passes validation; alert delivery will then fail, which is expected.

```sh
secret_dir=/tmp/osa-observability-secrets
sudo install -d -o root -g root -m 0711 "$secret_dir"
secret_file="$secret_dir/webhook-url"
printf '%s' 'https://hooks.example.invalid/local' | sudo tee "$secret_file" >/dev/null
sudo chown 472:0 "$secret_file"
sudo chmod 0400 "$secret_file"
export OSA_ALERT_WEBHOOK_URL_FILE="$secret_file"
```

**Start.** The launcher validates the webhook configuration first and prints only generic messages, never the URL:

```sh
scripts/start_observability.sh up --detach
docker compose -f observability/compose.yaml ps
```

All five services should be running. Published ports bind to `127.0.0.1` only; override them with `OSA_GRAFANA_PORT`, `OSA_PROMETHEUS_PORT`, `OSA_LOKI_PORT`, `OSA_TEMPO_HTTP_PORT`, `OSA_OTLP_GRPC_PORT` and `OSA_OTLP_HTTP_PORT`.

## 2. Sign in to Grafana

Open <http://127.0.0.1:3000>. The user is `admin` and the password is the value of `GRAFANA_ADMIN_PASSWORD`. Anonymous access is disabled.

Nothing needs to be added by hand. Grafana provisions, from files in `observability/`:

- Three data sources: Prometheus (`osa-prometheus`), Loki (`osa-loki`), Tempo (`osa-tempo`).
- The **OSA Operations** dashboard, in the **OSA** folder.
- The `OSARepeatedDatasetCreationFailures` alert rule, in the `osa-reliability` group, and the **OSA Test Webhook** contact point.

Check Connections, Data sources to see the three data sources.

## 3. Run the application so it exports telemetry

The Collector ports are published on `127.0.0.1` only, so an application inside a container cannot reach them. Run the backend on the host. The root README's `docker compose up` does not export telemetry by default.

When an OTLP endpoint is set, the application requires `OSA_OTLP_TOKEN_FILE` and sends it as a bearer token. The local Collector does not check it, so any valid token works. Characters are limited to letters, digits, `_` and `-`:

```sh
token_file=/tmp/osa-local-otlp-token
( umask 077; openssl rand -hex 32 > "$token_file" )

export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OSA_OTLP_TOKEN_FILE="$token_file"
export OSA_ENVIRONMENT=development   # development or production only
export OSA_VERSION=local-demo        # appears in the dashboard's Deployed version filter

uv run uvicorn app.main:app --app-dir backend
```

`OTEL_EXPORTER_OTLP_PROTOCOL` must be exactly `http/protobuf`. The service resource attributes `service.version` and `deployment.environment.name` come from `OSA_VERSION` and `OSA_ENVIRONMENT`.

## 4. Generate traffic

The sample-dataset endpoint takes no body and returns `201`:

```sh
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8000/api/datasets/sample
done
```

## 5. Check that data arrives

1. Open <http://127.0.0.1:9090/targets>. The `otelcol-internal` and `osa-application` targets should be **UP**.
2. In Grafana, open Explore and check each signal:
   - Prometheus: `osa_dataset_operations_total`
   - Loki: the application's log stream
   - Tempo: Search, to list recent traces

If a signal is missing, see the troubleshooting table.

## 6. Use the OSA Operations dashboard

Open Dashboards, the **OSA** folder, then **OSA Operations**, and set the time range to the last 15 minutes.

- The **Environment** filter offers `development` and `production`. **Deployed version** is discovered from telemetry, so `local-demo` appears once data arrives. Metric panels, annotations and the Loki and Tempo drill-down links all use both selections.
- The dashboard covers release identity and deployment annotations, request traffic and reliability, dataset creation and cleanup, analytics and DuckDB operations, runtime capacity, observability storage, and Collector exports.
- **No data is not zero.** It means no samples match the selected environment and version, so telemetry is missing or a scrape or export path is down. Check the filters and the Prometheus targets first, then use the filtered log and trace links.

## 7. Trigger the alert locally (optional)

`OSARepeatedDatasetCreationFailures` sums ten-minute increases of internal dataset and sample creation failures by service, environment and deployed version. It becomes pending at three failures and fires only if the condition holds for five minutes. Validation rejections are not counted.

With the same `OTEL_*` and `OSA_*` variables exported as in step 3, run the controlled-failure utility from the repository root. It runs only when `OSA_ENVIRONMENT=development`, produces exactly three internal creation failures against temporary storage, and cleans that storage up:

```sh
PYTHONPATH=backend uv run python -m app.controlled_failure --confirm-controlled-failure
```

Then open Alerting, Alert rules, group `osa-reliability`. The rule moves from Normal to Pending, and after about five minutes to Firing. With a placeholder webhook, delivery fails; inspect Alerting, Contact points, **OSA Test Webhook** for the receiver status. Once the failures age out of the ten-minute window the alert returns to Normal. Each alert instance carries `service`, `environment`, `deployed_version`, `severity=critical` and `owner=osa-maintainer`, and links to the [repeated creation failure runbook](../observability/runbooks/osa-repeated-dataset-creation-failures.md).

## 8. Stop and clean up

```sh
docker compose -f observability/compose.yaml down              # removes containers, keeps data
docker compose -f observability/compose.yaml down --volumes    # also deletes the stack's data
rm -f /tmp/osa-local-otlp-token
sudo rm -rf /tmp/osa-observability-secrets
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `GRAFANA_ADMIN_PASSWORD is required` | Export the password in the same terminal. |
| `Set OSA_ALERT_WEBHOOK_URL_FILE to a protected external file` | The variable is not exported. This also applies when you run `docker compose` directly instead of the launcher. |
| `Set the protected webhook URL file to mode 0400` or `…owner to Grafana container UID 472` | Repeat the `sudo chown 472:0` and `sudo chmod 0400` steps. |
| `must be an absolute path outside the repository` | Keep the secret file outside the checkout, for example under `/tmp`. |
| The app fails with `OSA_OTLP_TOKEN_FILE is required when an OTLP endpoint is set` | Create the token file and export `OSA_OTLP_TOKEN_FILE` (step 3). |
| `OTEL_EXPORTER_OTLP_PROTOCOL must be 'http/protobuf'` | Set that exact value. |
| Dashboard shows No data | `OSA_VERSION` or `OSA_ENVIRONMENT` does not match the filters, or the `osa-application` target is down. |
| A port is already in use | Override it with the matching `OSA_*_PORT` variable. |
| Export problems | `docker compose -f observability/compose.yaml logs collector`. Logs and traces use bounded queues and drop telemetry on overflow rather than blocking the app. |

Do not run `docker compose config` with a real webhook URL, and do not paste webhook URLs or tokens into logs, issues or shell history.
