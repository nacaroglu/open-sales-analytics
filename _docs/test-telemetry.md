# Test telemetry sink

The test-only Collector lives in `docker-compose.test-telemetry.yaml` and extends the root `docker-compose.yaml`.
It accepts OTLP/gRPC and OTLP/HTTP on the internal Compose network and writes received records as JSON to
`/tmp/osa-telemetry.json` inside its container. Host-published ports are limited to OTLP/HTTP and health,
both bound to loopback (`127.0.0.1`). No vendor account or external telemetry service is used.

Start the application and sink together with:

```sh
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml up --build --detach
```

The application receives `OTEL_EXPORTER_OTLP_ENDPOINT=http://telemetry-collector:4318` and
`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` from the test override. The Collector image has no shell utilities.
Copy its JSON-lines sink to the checkout to inspect captured records:

```sh
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml cp telemetry-collector:/tmp/osa-telemetry.json ./.osa-test-telemetry.json
cat ./.osa-test-telemetry.json
```

Remove the copied output, app, Collector, and Compose-managed data volume with:

```sh
docker compose -f docker-compose.yaml -f docker-compose.test-telemetry.yaml down --volumes --remove-orphans
rm -f ./.osa-test-telemetry.json
```

The captured JSON exists only in the Collector container's ephemeral filesystem until copied for inspection; the cleanup command removes both the copied output and the service.
CI uses synthetic telemetry only and does not print credentials or production data.
