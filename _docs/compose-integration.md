# Compose integration checks

Run the container integration matrix locally with Docker Compose v2:

```sh
python3 scripts/compose_integration.py
```

The runner builds and starts the real app in an isolated self-hosted project, then starts a separate
public-demo project using the same built image. It checks readiness, the built HTML/JS/CSS and SPA
fallback, sample analytics response shapes against the app's OpenAPI document, valid and invalid
uploads, token protection, deletion, expiry polling, and public-demo upload rejection. It prints a
PASS line for each completed integration case. Failure output identifies the case and includes
bounded Compose status/log diagnostics.

The self-hosted run uses a 45-second dataset TTL to exercise expiry without waiting for the default
24-hour lifetime. Each run gets a unique Compose project, ephemeral dataset volume, and local telemetry
output directory. Both projects are stopped with `down --volumes`; the runner verifies that their
containers and named volumes are gone, then removes their local output directories, including on an
ordinary test failure.

IT-08 invokes the private `app.telemetry_test_signal` command inside the running app container. It
sets `PYTHONPATH=/app/backend`, `OSA_ENVIRONMENT=development`, and `OSA_VERSION=integration-test`,
then waits up to 30 seconds for the test Collector file sink. The harness checks that synthetic trace,
metric, and log records each carry `service.name=open-sales-analytics`, `service.namespace=osa`,
`deployment.environment.name=development`, and `service.version=integration-test`. It reports only a
PASS/FAIL line and never prints the sink contents. The application identity and synthetic signal are
provided by [#253](https://github.com/nacaroglu/open-sales-analytics/issues/253); the local Collector
is defined by [#230](https://github.com/nacaroglu/open-sales-analytics/issues/230).
