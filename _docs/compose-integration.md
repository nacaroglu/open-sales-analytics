# Compose integration checks

Run the container integration matrix locally with Docker Compose v2:

```sh
make integration
```

From the repository root, the contributor commands are:

- `make build` validates the base Compose configuration and builds the application image.
- `make integration` runs IT-01 through IT-08 and cleans both isolated projects on success or failure.
- `make e2e` starts the built app through Compose, waits for readiness, and runs the Chromium journey with
  `E2E_BASE_URL` set to that app.
- `make clean` removes Compose resources and telemetry sink directories scoped to this checkout and user.

Docker Engine with Compose v2 is required for all four commands. Integration also needs Python 3. The E2E
command needs Node.js 22, installed frontend packages (`cd frontend && npm ci`), and the Chromium browser and
system libraries (`npx playwright install chromium` and, on Linux, `npx playwright install-deps chromium`).
Set `OSA_E2E_PORT` to use a specific available host port; otherwise the command selects an ephemeral port.
Every run has a unique Compose project name and a private temporary root with a random owner token. `make clean`
verifies each marker, derives the exact project names created for that run, and removes only those projects and sinks.
It does not run Docker prune or remove host datasets.

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
