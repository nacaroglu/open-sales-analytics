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
