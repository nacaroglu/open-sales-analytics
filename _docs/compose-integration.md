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

IT-08 resource-identity assertions are coupled to the application's instrumentation contract in
[#253](https://github.com/nacaroglu/open-sales-analytics/issues/253). The test Collector used by the
suite is defined in [#230](https://github.com/nacaroglu/open-sales-analytics/issues/230).
