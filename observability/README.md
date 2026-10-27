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
Set `OSA_GRAFANA_ROOT_URL` to the public HTTPS root when Grafana is behind a
reverse proxy; the alert dashboard link uses Grafana's configured root URL.

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

The AWS Collector uses a separate authenticated configuration. Its OTLP receivers
require a bearer token and read the development and production tokens from a
root-owned runtime secret file. Store each token as an SSM `SecureString` at
`/osa/dev/observability/otlp-token` and `/osa/prod/observability/otlp-token`;
the application roles can read only their own environment's parameter. Do not
put either value in CloudFormation parameters, user data, GitHub variables,
Compose environment values, or logs. The deployed app stack fetches its token at
startup into a read-only file mount. Local app Compose has no OTLP endpoint by
default, creates no exporter, and needs no AWS credentials.

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

Each alert instance carries `service`, `environment`, `deployed_version`,
`severity=critical`, and `owner=osa-maintainer`. The environment and version
labels filter the dashboard link. Its values are allowlisted; missing or
malformed values render as `unknown`, so telemetry cannot add query parameters
or redirect the link. The alert also links to the Git-versioned
[repeated creation failure runbook](runbooks/osa-repeated-dataset-creation-failures.md),
which explains how to correlate privacy-safe Loki records with Tempo traces.

### Test webhook delivery

The alert routes directly to the provisioned **OSA Test Webhook** contact point
(`osa-test-webhook`). No other alert or application notification is routed to
it. Grafana's webhook receiver sends the alert name/status, bounded rule labels
and annotations, and standard delivery metadata. It caps each webhook group at
ten alert instances. The rule annotations contain only the fixed impact text,
filtered Grafana/runbook links, and privacy-safe Loki/Tempo guidance.

The endpoint is a protected runtime secret file, never a Compose variable or a
repository file. Create a root-controlled directory outside this checkout, then
enter the receiver URL silently. The secret file must be owned by Grafana's
container UID 472 and have mode 0400. Use an HTTPS receiver URL; provider tokens
may be part of its protected path or query string. Do not use URL user-info.
Grafana alone joins the dedicated `webhook-egress` network to reach that
receiver; the Collector, Prometheus, Loki, and Tempo remain on the private
observability network, and the egress network publishes no ports.

```sh
secret_dir=/tmp/osa-observability-secrets
sudo install -d -o root -g root -m 0711 "$secret_dir"
secret_file="$secret_dir/webhook-url"
read -rsp 'Test webhook URL: ' webhook_url; printf '\n'
printf '%s' "$webhook_url" | sudo tee "$secret_file" >/dev/null
unset webhook_url
sudo chown 472:0 "$secret_file"
sudo chmod 0400 "$secret_file"
export OSA_ALERT_WEBHOOK_URL_FILE="$secret_file"
scripts/start_observability.sh up --detach
unset OSA_ALERT_WEBHOOK_URL_FILE
```

The launcher runs `scripts/validate_alert_webhook_config.py` before Compose and
prints only generic validation messages, never the endpoint or token. CI uses
an ephemeral synthetic HTTPS value and static tests; it does not contact a
webhook, Grafana, or AWS. Do not run `docker compose config` with a real endpoint
or copy endpoint values into logs, issue comments, shell history, or support
bundles. The Grafana entrypoint reads the mounted file at startup and removes
the value from its shell variable before starting Grafana. Grafana's
provisioned contact-point URL is a protected receiver setting.

To diagnose delivery, inspect **Alerting → Contact points → OSA Test Webhook**
and Grafana's notification history for receiver status, retry, or timeout
errors. Check that the protected file still passes preflight and that the host
can reach the receiver over HTTPS. Share only the receiver UID and generic
delivery status; redact any provider URL or credentials from detailed errors.

CI runs offline checks for data-source UIDs/endpoints, dashboard rows and
panels, filters, links, no-data guidance, and the alert's metric expression and
state transitions. These checks do not require Grafana or an observability
backend.

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

## Authenticated application OTLP rotation and verification

Application OTLP uses the private `CollectorPrivateEndpoint` on TCP 4318. The app security group permits egress only to `CollectorSecurityGroupId`, and Collector ingress is restricted to the matching app security group. There is no public OTLP listener. Keep separate SSM `SecureString` tokens at `/osa/dev/observability/otlp-token` and `/osa/prod/observability/otlp-token`.

For rotation, generate a new URL-safe value into a mode-restricted temporary file, set `OTLP_TOKEN_PARAMETER` to the environment's parameter path, and use `aws ssm put-parameter --name "$OTLP_TOKEN_PARAMETER" --type SecureString --value "file://$TOKEN_FILE" --overwrite >/dev/null`. Do not print or decrypt the value. Use Session Manager to restart `osa-observability.service` on the Collector instance and `osa-compose.service` on that environment's app instance so each reloads the parameter. Confirm both units are active.

To verify ingestion, run `docker compose --env-file /opt/osa/.env -f /opt/osa/compose.yaml exec -T app env PYTHONPATH=/app/backend OSA_ENVIRONMENT=development python -m app.telemetry_test_signal` from the dev app instance; use `OSA_ENVIRONMENT=production` on prod. The command emits a synthetic trace, metric, and log using the configured private endpoint and token file. Confirm it reports a successful flush, then use Grafana Explore to find `osa.synthetic.resource_identity` in Tempo, Prometheus, and Loki and check the service and environment resource attributes. Preflight checks verify only that the parameter exists as a `SecureString`; they never decrypt or display its value.
