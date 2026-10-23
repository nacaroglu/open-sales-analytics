# Open Sales Analytics — Phase 4 Productionization and Observability Specification

**Status:** Scope agreed  
**Date:** 2026-10-23  
**Project:** Open Sales Analytics (OSA)  
**Phase objective:** Build, deploy, observe, promote, demonstrate, and completely tear down a production-style OSA environment using reproducible infrastructure and immutable releases.

## 1. Executive Summary

Phase 4 is a **reproducible production simulation** for the Open Sales Analytics portfolio project. It applies production engineering practices without turning OSA into a hosted multi-tenant SaaS.

The phase will:

- package the React frontend and FastAPI backend as one production image;
- run the application locally through Docker Compose;
- test the complete containerized system;
- provision shared, development, production, and observability infrastructure with AWS CloudFormation;
- build immutable images in CI and push them to Amazon ECR;
- deploy automatically to development and promote the exact tested image manually to production;
- instrument the backend with OpenTelemetry;
- collect metrics, logs, and traces through a separate observability stack;
- provide a filtered Grafana operations dashboard and one actionable alert;
- capture demonstration evidence;
- destroy all AWS resources after the demonstration.

The work is divided into three increments:

| Increment | Name | Outcome |
| --- | --- | --- |
| **4A** | Container & Test Foundation | Production image, Compose workflow, health contract, integration tests and Playwright |
| **4B** | AWS Delivery Pipeline | CloudFormation, ECR, GitHub OIDC, dev/prod deployment, immutable promotion and rollback |
| **4C** | Observability & Demonstration | OpenTelemetry, Grafana stack, metrics, dashboard, alert, evidence and teardown |

## 2. Reference Workflow and OSA Adaptation

Phase 4 follows the workflow described in:

- [Deploy a Full-Stack App with AI Coding Assistants](https://aishippingblog.com/p/deploy-a-full-stack-app-with-ai-coding)
- [DevOps and Observability for an AI-Built App](https://aishippingblog.com/p/devops-and-observability-for-an-ai)

The reference application has persistent Postgres data and a collaborative canvas. OSA differs in two important ways:

1. The public deployment remains sample-only and has no durable customer data.
2. The canvas-specific alert is replaced by an OSA dataset-creation alert.

Therefore, Phase 4 does not add Postgres, public CSV uploads, accounts, or customer-data persistence merely to copy the reference architecture.

## 3. Product and Operational Scope

### 3.1 Product user

The public user is an evaluator who loads the synthetic sample and explores Overview, Customer, and Product analytics.

The AWS deployment does not accept arbitrary files. Full CSV upload remains available in the self-hosted application.

### 3.2 Operator

The operator is a solo maintainer who needs to:

- verify changes before release;
- deploy the same artifact consistently;
- promote a tested version from development to production;
- see which environment and version are failing;
- move from an alert to the relevant dashboard, logs, and traces;
- reproduce and safely remove the complete environment.

### 3.3 Core operational job

> Build one immutable OSA image, prove it works in the complete stack, deploy it to development, promote exactly that image to production, observe real behavior, diagnose failures, and remove all cloud resources cleanly after the demonstration.

### 3.4 Success principles

- Build once; promote the same image digest.
- Infrastructure is code, not a sequence of undocumented console actions.
- Health checks prove readiness, not only process existence.
- Metrics show impact; logs explain events; traces show request paths.
- Environment and deployed version are visible throughout telemetry.
- User-controlled values never become metric labels.
- No permanent cloud footprint is required for portfolio value.

## 4. Data and Application Boundaries

### 4.1 Dataset contract

Phase 4 makes **no changes** to the Phase 3 sales-data contract, validation rules, analytics formulas, or customer privacy model.

### 4.2 AWS data behavior

- Public dev and production deployments run in sample-only mode.
- Arbitrary upload endpoints are disabled server-side.
- Generated DuckDB files are temporary.
- Application data is stored only in an ephemeral container/host volume.
- A restart or deployment may delete active temporary datasets.
- The deterministic sample can always be recreated.
- No EBS, S3, RDS, backup, migration, or recovery promise applies to application data.

### 4.3 Durable Phase 4 data

Only the following is retained while the demonstration infrastructure exists:

- immutable container images in ECR;
- seven days of bounded telemetry;
- CloudFormation state;
- deployed-version metadata.

All are deleted during final teardown. Code, dashboards, runbooks, test reports, screenshots, architecture documentation, and benchmark evidence remain in the repository or release artifacts.

## 5. Phase 4A — Container & Test Foundation

### 5.1 Production Dockerfile

Create one multi-stage Dockerfile:

1. **Frontend build stage**
   - use a pinned Node base image;
   - install dependencies from the lockfile;
   - run frontend checks and build the React application;
   - output static assets only.
2. **Backend runtime stage**
   - use a pinned slim Python base image;
   - install locked production dependencies;
   - copy backend code and compiled frontend assets;
   - run FastAPI with a production ASGI server configuration;
   - serve both API and SPA assets from the backend.

Runtime requirements:

- Node and frontend source are absent from the final image;
- the container runs as a non-root user;
- only the application port is exposed;
- writable paths are limited to temporary data and `/tmp`;
- configuration is supplied through environment variables;
- build metadata supplies the readable version;
- the image contains a container health check or Compose uses the readiness endpoint;
- no credential or environment-specific configuration is baked into the image.

### 5.2 Compose structure

Use two layers:

- `docker-compose.yaml`: application service used locally and in integration tests;
- deployment override: application plus Caddy, pulling the specified ECR image rather than building it.

The base command remains:

```bash
docker compose up --build
```

The base application runs without Caddy to avoid local certificate friction. Deployment uses Caddy for HTTPS and ingress.

The separate `observability/` Compose project must not be merged into the application Compose project.

### 5.3 Health contract

#### `GET /health/live`

Confirms that the application process can respond.

- no downstream dependency checks;
- suitable for container liveness;
- returns HTTP 200 when alive.

#### `GET /health/ready`

Confirms that the instance can serve OSA:

- application initialization completed;
- temporary storage is writable;
- a minimal DuckDB probe succeeds;
- required sample assets/configuration are available.

Successful responses contain only:

```json
{
  "status": "ready",
  "service": "open-sales-analytics",
  "environment": "development",
  "version": "20261023-173000-83242da"
}
```

No hostname, filesystem path, credential, stack ID, account ID, or secret is returned.

### 5.4 Compose integration-test matrix

Integration tests start the real Compose stack and verify:

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| IT-01 | Container startup | Application reaches readiness within the timeout |
| IT-02 | Frontend delivery | FastAPI serves built HTML, JS, CSS and SPA route fallback |
| IT-03 | Sample workflow | Sample loads and Overview, Customer and Product APIs return valid responses |
| IT-04 | Self-hosted valid upload | Valid CSV creates a token-protected temporary dataset |
| IT-05 | Invalid upload | Entire upload is rejected and no dataset remains |
| IT-06 | Dataset access lifecycle | Token authorization, explicit deletion and expiry behave correctly |
| IT-07 | Public-demo mode | Upload is rejected server-side while sample mode works |
| IT-08 | Telemetry identity | Exported telemetry contains service, environment and version attributes |

IT-08 may use a test-only Collector/OTLP sink through a Compose test override. It must not require the complete production observability stack.

Metric-formula correctness remains in existing unit and golden-dataset tests; it is not duplicated through Compose.

### 5.5 Playwright journey

One browser test runs against Compose:

1. Open the built application.
2. Load the sample dataset.
3. Verify Overview renders.
4. Change the reporting period/comparison.
5. Visit Customer analytics and verify representative content.
6. Visit Product analytics and verify representative content.
7. Verify the browser sees no failed API requests or uncaught application errors.

## 6. Phase 4B — AWS Infrastructure

### 6.1 Stack model

| Stack | Responsibility |
| --- | --- |
| `osa-foundation` | VPC, subnets, routing, ECR, GitHub OIDC provider, base IAM roles and shared parameters |
| `osa-dev` | Development EC2, security group, Elastic IP/DNS, Caddy and application runtime |
| `osa-prod` | Production EC2, security group, Elastic IP/DNS, Caddy and application runtime |
| `osa-observability` | Observability EC2, security group, volumes, Caddy/Grafana and telemetry services |

`osa-dev` and `osa-prod` are separate CloudFormation stack instances of the same parameterized application template. Environment differences are parameters, not copied templates.

The observability stack imports the shared network. Application stacks receive the private Collector endpoint as configuration.

### 6.2 Network and ingress

- Caddy terminates HTTPS for development, production and Grafana.
- Production is publicly accessible in sample-only mode.
- Development requires Caddy basic authentication.
- Grafana requires authentication.
- Only required HTTPS/HTTP ingress is public.
- There is no public SSH; administration uses AWS Systems Manager Session Manager or Run Command.
- OTLP ports are not public.
- The Collector security group accepts OTLP only from dev and production application security groups.
- Application instances send telemetry to the Collector through private VPC addressing.
- Outbound access is limited to what image pull, certificate acquisition, package/runtime operation and AWS management require.

The deployment assumes a user-controlled DNS zone or equivalent DNS records for dev, production, and Grafana hostnames.

### 6.3 Application persistence

Application stacks use only ephemeral data storage for temporary DuckDB files. Deployments do not mount a durable application-data EBS volume.

### 6.4 ECR policy

- Repository tag mutability is `IMMUTABLE`.
- Human-readable version format is `YYYYMMDD-HHMMSS-shortsha` using UTC.
- Example: `20261023-173000-83242da`.
- CI resolves the pushed image to its ECR digest.
- CloudFormation deploys `repository@sha256:digest`.
- The readable tag is passed separately as `service.version`.
- Repository lifecycle configuration prevents uncontrolled accumulation during repeated demonstrations.
- Final teardown deletes all ECR images and the repository.

### 6.5 Caddy deployment

The deployment Compose override contains:

- application service pinned to the supplied image digest;
- Caddy service with environment-specific hostname and access policy;
- health-aware startup/restart configuration;
- no image build step.

Development basic-auth material is injected from SSM Parameter Store. Production does not require application authentication because it exposes only the synthetic sample workflow.

## 7. IAM and Secret Management

### 7.1 GitHub OIDC

GitHub Actions uses OIDC to obtain temporary AWS credentials. No long-lived AWS access key is stored in GitHub.

Trust policies must restrict:

- audience to `sts.amazonaws.com`;
- repository owner and repository;
- expected branch or GitHub environment;
- production role assumption to the protected production environment.

### 7.2 Role separation

| Role | Allowed purpose |
| --- | --- |
| Build role | Authenticate and push only to the OSA ECR repository |
| Dev deploy role | Update/read only the development stack and invoke required dev deployment operations |
| Production promotion role | Update/read only the production stack after protected manual approval |
| Foundation execution role | Create/delete shared network, ECR and OIDC resources |
| Application-stack execution role | Create/delete one app environment's declared resources |
| Observability execution role | Create/delete the observability stack's declared resources |
| EC2 instance role | Pull the approved ECR image and use Systems Manager; no general AWS access |

Roles follow least privilege and use resource restrictions wherever the AWS API supports them. Deployment roles may pass only the intended CloudFormation execution role.

### 7.3 Secrets

Store as SSM Parameter Store `SecureString` values:

- development Caddy credential/hash;
- Grafana administrator credential;
- OTLP authentication token;
- any webhook secret required for the alert demonstration.

Do not place secrets in:

- Git history;
- Docker images;
- CloudFormation outputs;
- EC2 user-data logs;
- GitHub repository variables;
- telemetry or health responses.

OIDC role ARNs, stack names, region, repository name, hostnames and dashboard URLs are non-secret configuration.

## 8. CI/CD Workflows

### 8.1 Pull-request CI

Required jobs:

1. Backend tests and checks.
2. Frontend tests and checks, running in parallel with backend tests.
3. Production Docker image build.
4. Compose integration tests.
5. Playwright end-to-end test.
6. CloudFormation template validation and linting.
7. Observability configuration validation where tooling is available.

No pull request deploys to AWS.

### 8.2 Development delivery on `main`

After required tests pass:

1. Generate the UTC version tag.
2. Build the application image once.
3. Push the version tag to immutable ECR.
4. Resolve and record the digest.
5. Update `osa-dev` with the digest and readable version.
6. Wait for `/health/ready`.
7. Run the sample-dashboard smoke check.
8. Record the deployed digest/tag in stack outputs or deployment metadata.

No image is built on EC2.

### 8.3 Manual production promotion

The workflow uses `workflow_dispatch` and the protected GitHub production environment:

1. Read the digest and version currently deployed in dev.
2. Require manual production approval.
3. Record the current production digest for rollback.
4. Update production with the exact dev digest—without rebuilding or retagging.
5. Wait for production readiness.
6. Run the production sample-dashboard smoke check.
7. On failure, restore the previous production digest and verify readiness again.
8. Report promoted version, digest, health result and rollback result.

### 8.4 Deployment verification

Readiness alone is necessary but insufficient. The post-deploy smoke test must exercise the sample creation/API path and verify representative analytics content.

## 9. Phase 4C — OpenTelemetry Instrumentation

### 9.1 Resource identity

Every metric, log, and trace uses standard OpenTelemetry resource attributes:

| Attribute | Value |
| --- | --- |
| `service.name` | `open-sales-analytics` |
| `service.namespace` | `osa` |
| `service.version` | Readable immutable image version |
| `deployment.environment.name` | `development` or `production` |

Environment and version are resource attributes rather than manually repeated unbounded event labels.

### 9.2 Automatic instrumentation

Instrument FastAPI/ASGI and supported HTTP/runtime libraries to capture:

- server request spans;
- request count and duration;
- response status/error classification;
- context propagation.

### 9.3 Manual domain spans

Add bounded, named spans around:

- sample dataset creation;
- CSV validation;
- DuckDB canonical import;
- Overview query execution;
- Customer query execution;
- Product query execution;
- dataset cleanup.

Span attributes may contain bounded categories such as module, source, outcome and row-count bucket. They must not contain dataset IDs, tokens, filenames, customer/order/product IDs, query strings, raw CSV values or SQL text containing user data.

### 9.4 Logs

Emit structured logs containing:

- timestamp;
- severity;
- event/message;
- trace ID and span ID when available;
- service, environment and version;
- bounded operation/outcome/error code.

Privacy-safe logging rules from earlier phases remain. Customer data, bearer tokens, CSV contents and business identifiers are forbidden.

### 9.5 Trace sampling

- Capture 100% of backend traces in development and production for this low-traffic demonstration.
- Keep the sampling rate configurable by environment.
- Metrics and logs are not sampled.
- Seven-day retention and storage limits remain the primary volume controls.

## 10. Observability Stack

Create `observability/` as an independent Compose project containing:

- OpenTelemetry Collector;
- Prometheus;
- Loki;
- Tempo;
- Grafana.

### 10.1 Signal routing

```text
OSA dev/prod --OTLP--> OpenTelemetry Collector
Collector --metrics--> Prometheus
Collector --logs-----> Loki
Collector --traces---> Tempo
Grafana reads Prometheus, Loki and Tempo
```

The Collector also exposes its own operational/export-failure metrics to Prometheus.

### 10.2 Retention and storage

- Metrics, logs, and traces retain seven days.
- Storage resides on encrypted EBS attached to the observability instance.
- Prometheus, Loki and Tempo use explicit retention/storage limits.
- Disk-usage panels and warnings make capacity visible.
- Telemetry volumes are deleted during final teardown.
- Dashboards, data-source definitions, Collector configuration and alert rules are provisioned from Git.
- There is no telemetry backup or archive.

## 11. Metric Catalogue

Exact library-generated HTTP metric names may follow the selected stable semantic-convention version. Custom OSA metrics use a consistent `osa.` namespace.

### 11.1 HTTP and runtime

| Metric | Type | Dimensions |
| --- | --- | --- |
| HTTP server request count | Counter | method, route template, status class |
| HTTP server duration | Histogram | method, route template, status class |
| Active HTTP requests | Up-down counter | route template |
| Unhandled application errors | Counter | bounded exception category |
| Process CPU utilization | Gauge | none beyond resources |
| Process memory usage | Gauge | none beyond resources |
| `osa.app.starts` | Counter | outcome |
| `osa.app.uptime` | Gauge | none beyond resources |
| Temporary-storage free bytes | Gauge | storage class only |

### 11.2 Dataset lifecycle

| Metric | Type | Dimensions |
| --- | --- | --- |
| `osa.dataset.operations` | Counter | operation, source=`sample|upload`, outcome, bounded failure class |
| `osa.dataset.processing.duration` | Histogram | operation, source, outcome |
| `osa.dataset.rows` | Histogram | source, outcome |
| `osa.dataset.active` | Observable gauge | source |
| `osa.dataset.cleanup.failures` | Counter | bounded failure class |

### 11.3 Validation

| Metric | Type | Dimensions |
| --- | --- | --- |
| `osa.validation.rejections` | Counter | documented bounded error code |

Validation rejections are product feedback, not service failures, and do not trigger the operational alert.

### 11.4 Analytics

| Metric | Type | Dimensions |
| --- | --- | --- |
| `osa.analytics.requests` | Counter | module=`overview|customer|product`, outcome |
| `osa.analytics.duration` | Histogram | module, outcome |
| `osa.duckdb.operations` | Counter | bounded operation name, outcome |
| `osa.duckdb.duration` | Histogram | bounded operation name, outcome |

### 11.5 Collector health

Track Collector receive/export counts, dropped telemetry, queue pressure, and export failures using Collector self-telemetry.

### 11.6 Cardinality policy

Allowed dimensions are enumerated in code/tests. The following are prohibited from metric labels:

- dataset, order, product or customer identifiers;
- bearer tokens;
- filenames or file paths;
- full URLs or query strings;
- exception messages;
- arbitrary validation text;
- Git commit messages;
- raw user input.

## 12. Grafana Operations Dashboard

Provision one **OSA Operations** dashboard.

### 12.1 Variables

- `environment`: development or production;
- `deployed_version`: values observed in telemetry.

Every application panel respects both filters.

### 12.2 Dashboard rows

1. **Release identity**
   - current service/environment/version;
   - application uptime/start count;
   - deployment annotations.
2. **Traffic and reliability**
   - request rate;
   - 5xx/error rate;
   - p50, p95 and p99 latency;
   - active requests.
3. **Dataset workflow**
   - sample/upload attempts by outcome;
   - internal creation failures;
   - processing-duration percentiles;
   - rows processed;
   - active temporary datasets and cleanup failures.
4. **Analytics**
   - request rate, failures and latency by Overview/Customer/Product;
   - DuckDB duration and failures by bounded operation.
5. **Runtime and capacity**
   - process CPU and memory;
   - temporary-storage free space;
   - observability disk usage;
   - Collector export/drop failures.

Relevant panels link to pre-filtered Loki logs and Tempo traces. Deployment annotations show when a version changed.

## 13. Actionable Alert

### 13.1 Alert name

`OSARepeatedDatasetCreationFailures`

### 13.2 User-impact definition

Count only dataset/sample creation failures caused by internal application or infrastructure errors. Do not count invalid user CSVs or documented validation rejections.

### 13.3 Threshold

Fire when one service/environment/version produces at least three internal dataset-creation failures during a ten-minute window and the condition remains true for five minutes.

Illustrative PromQL after resource-attribute normalization:

```promql
sum by (service_name, deployment_environment_name, service_version) (
  increase(osa_dataset_operations_total{
    operation="create",
    outcome="failure",
    failure_class="internal"
  }[10m])
) >= 3
```

Grafana evaluates it with `for: 5m`.

### 13.4 Alert contents

Required labels/annotations:

- service;
- environment;
- deployed version;
- severity=`critical`;
- owner=`osa-maintainer`;
- concise impact summary;
- OSA Operations dashboard URL with environment/version filters;
- runbook URL;
- links or instructions for correlated logs and traces.

### 13.5 Notification and controlled verification

- Deliver the alert to a configurable test webhook contact point.
- Do not hard-code a personal notification endpoint.
- Demonstrate the rule in development by running an internal test utility inside the app container that invokes the dataset service with a deliberately failing temporary-storage configuration.
- Do not expose a public fault-injection HTTP endpoint.
- Capture the firing alert, webhook payload, dashboard, related logs and trace.
- Restore the healthy dev deployment and confirm that the alert resolves.

## 14. Security Requirements

- Production exposes only synthetic sample behavior.
- Development and Grafana require authentication.
- Caddy provides HTTPS.
- No public SSH exists.
- OTLP remains private within the shared VPC and requires its configured token.
- Secrets are retrieved from SSM at deployment/runtime and are never written to Git or telemetry.
- GitHub OIDC trust is limited to the intended repository, branch, workflow/environment and audience.
- Production promotion uses a distinct protected environment and role.
- EC2 does not build images or hold source-control credentials.
- Containers run without root when supported and expose only required ports.
- The app's writable paths are narrowly scoped.
- Logs and spans follow existing OSA privacy redaction rules.
- Grafana data sources and dashboards contain no embedded credentials.
- CloudFormation outputs must not expose secret values.

## 15. Demonstration and Evidence Plan

Before teardown, capture:

1. Successful PR CI jobs.
2. Immutable ECR tag and digest.
3. Automatic dev deployment and readiness/smoke results.
4. Manual production promotion showing the same digest.
5. Dev and production application pages.
6. Grafana dashboard filtered separately for each environment/version.
7. A representative request trace connected to logs.
8. Controlled dataset-creation failures and the firing/resolved alert.
9. Rollback demonstration or automated rollback test evidence.
10. CloudFormation stack/resource summary.
11. Final cleanup commands and successful deletion verification.

Evidence should be assembled into a concise release report without exposing account IDs, secrets, tokens, private addresses, or authentication data.

## 16. Teardown Plan

### 16.1 Policy

All Phase 4 AWS resources are temporary. Teardown is manual and approval-gated; it must never run automatically after an ordinary deployment.

### 16.2 Dependency order

1. `osa-dev`
2. `osa-prod`
3. `osa-observability`
4. `osa-foundation`

Each deletion waits for completion before the next begins.

Example per-stack pattern:

```bash
aws cloudformation delete-stack --stack-name osa-dev
aws cloudformation wait stack-delete-complete --stack-name osa-dev
```

### 16.3 Delete behavior

- ECR is configured for final empty-on-delete behavior because the user explicitly chose complete teardown.
- Observability EBS volumes use delete-on-termination/no retain policy.
- Elastic IPs, DNS records, security groups, SSM parameters and IAM roles created by the stacks are deleted.
- No snapshots or backups are retained.

### 16.4 Verification

The cleanup script/report verifies:

- all four stacks are absent;
- no OSA EC2 instances remain;
- no OSA EBS volumes or snapshots remain;
- no OSA Elastic IPs remain;
- the OSA ECR repository/images are absent;
- created Route 53 records are absent;
- created SSM parameters and OSA-specific IAM roles are absent.

Resources that predated Phase 4 or are explicitly supplied as external parameters must never be deleted.

## 17. Testing and Quality Gates

### 17.1 Unit and configuration tests

- health response semantics;
- resource-attribute configuration;
- custom metric increments and allowed dimensions;
- telemetry redaction;
- alert expression fixtures;
- image-tag format;
- promotion selects dev digest without rebuilding;
- rollback retains the previous digest.

### 17.2 Infrastructure checks

- CloudFormation validation/linting;
- least-privilege policy review;
- OIDC trust-policy tests or assertions;
- security-group assertions: no SSH, no public OTLP;
- no secret CloudFormation outputs;
- development and production templates resolve from the same source;
- destructive cleanup requires explicit manual confirmation.

### 17.3 Observability checks

- Collector configuration validates;
- Prometheus targets/Collector pipeline are healthy;
- Grafana data sources provision correctly;
- environment/version variables filter panels;
- metrics, logs and traces contain correct resource identity;
- forbidden high-cardinality attributes are absent;
- controlled failures fire and later resolve the alert.

## 18. Explicit Non-Goals

- permanent AWS hosting or an uptime SLA;
- public CSV uploads;
- user accounts or multi-tenancy;
- durable customer/application data;
- dataset-contract or business-analytics changes;
- Postgres, RDS or S3 dataset persistence;
- ECS, Fargate, Kubernetes or managed container orchestration;
- autoscaling, load balancing or multi-AZ high availability;
- blue/green, canary or zero-downtime deployment;
- frontend browser/RUM telemetry;
- telemetry retention beyond seven days;
- telemetry backups or long-term archive;
- more alert rules beyond repeated internal dataset-creation failures;
- paging rotations, SLA/SLO programs or incident-management integration;
- AI on-call responders or automated code repair;
- permanent operational ownership of the demonstration infrastructure.

## 19. Prioritized Backlog

### 19.1 Phase 4A — Container & Test Foundation

#### P0 — Container runtime

- **4A-01:** Implement the multi-stage Node/Python Dockerfile.
- **4A-02:** Serve React assets and SPA fallback through FastAPI.
- **4A-03:** Run the final container as non-root with scoped writable paths.
- **4A-04:** Add environment/version runtime configuration and build metadata.
- **4A-05:** Implement `/health/live` and `/health/ready`.
- **4A-06:** Create base `docker-compose.yaml` for local and test execution.
- **4A-07:** Create deployment Compose override for ECR image plus Caddy.

#### P0 — Stack tests

- **4A-08:** Implement IT-01 through IT-08 against Compose.
- **4A-09:** Add the test OTLP sink/Collector override.
- **4A-10:** Implement the cross-module Playwright sample journey.
- **4A-11:** Add Make/task commands for build, integration, E2E and cleanup.
- **4A-12:** Document local production-mode startup and troubleshooting.

### 19.2 Phase 4B — AWS Delivery Pipeline

#### P0 — Infrastructure

- **4B-01:** Create the `osa-foundation` CloudFormation template.
- **4B-02:** Provision shared VPC/networking and security-group boundaries.
- **4B-03:** Provision immutable ECR with bounded lifecycle and final empty-on-delete behavior.
- **4B-04:** Provision GitHub OIDC provider and separate least-privilege roles.
- **4B-05:** Create one parameterized application CloudFormation template.
- **4B-06:** Instantiate independent `osa-dev` and `osa-prod` stacks.
- **4B-07:** Configure EC2, ECR pull, Systems Manager, Caddy, DNS and HTTPS.
- **4B-08:** Configure dev authentication and sample-only server mode.
- **4B-09:** Add SSM SecureString references without secret outputs/logging.

#### P0 — CI/CD

- **4B-10:** Run backend and frontend jobs in parallel for pull requests.
- **4B-11:** Build the production image and run Compose integration/E2E jobs.
- **4B-12:** Validate CloudFormation and security assertions in CI.
- **4B-13:** Generate UTC `YYYYMMDD-HHMMSS-shortsha` versions.
- **4B-14:** Push immutable image to ECR and resolve its digest.
- **4B-15:** Deploy the digest automatically to dev after merge to `main`.
- **4B-16:** Verify dev readiness and sample workflow.
- **4B-17:** Implement protected manual promotion of the exact dev digest.
- **4B-18:** Verify production and automatically restore the previous digest on failure.
- **4B-19:** Record deployment evidence without exposing sensitive infrastructure values.

### 19.3 Phase 4C — Observability & Demonstration

#### P0 — Telemetry

- **4C-01:** Configure OpenTelemetry resource attributes using service/environment/version conventions.
- **4C-02:** Add FastAPI/ASGI auto-instrumentation.
- **4C-03:** Add manual spans for dataset and analytics operations.
- **4C-04:** Emit structured trace-correlated, privacy-safe logs.
- **4C-05:** Implement the focused custom metric catalogue.
- **4C-06:** Add cardinality/redaction tests and 100% configurable trace sampling.

#### P0 — Observability stack

- **4C-07:** Create independent `observability/` Compose project.
- **4C-08:** Configure Collector routing to Prometheus, Loki and Tempo.
- **4C-09:** Provision Grafana data sources and the OSA Operations dashboard.
- **4C-10:** Implement seven-day retention, encrypted storage and storage caps.
- **4C-11:** Create the `osa-observability` CloudFormation stack.
- **4C-12:** Connect dev/prod to private authenticated OTLP ingestion.

#### P0 — Alert, evidence and teardown

- **4C-13:** Provision `OSARepeatedDatasetCreationFailures`.
- **4C-14:** Add dashboard/runbook links, owner, severity, environment and version annotations.
- **4C-15:** Configure the test webhook contact point.
- **4C-16:** Create the non-public controlled failure utility.
- **4C-17:** Demonstrate alert firing and resolution in dev.
- **4C-18:** Capture the agreed deployment/observability evidence report.
- **4C-19:** Implement guarded ordered teardown commands/workflow.
- **4C-20:** Verify removal of all Phase 4-created AWS resources.

## 20. Acceptance Criteria

### 20.1 Phase 4A is complete when

1. `docker compose up --build` starts the complete application locally.
2. The final image contains compiled frontend assets but no Node runtime/dependencies.
3. FastAPI serves API and SPA routes.
4. Liveness and readiness follow the documented contract.
5. IT-01 through IT-08 pass.
6. The Playwright sample journey passes against Compose.

### 20.2 Phase 4B is complete when

1. All four stacks can be created from CloudFormation without undocumented console resources.
2. GitHub uses OIDC with separate least-privilege roles and no AWS access keys.
3. A merge to `main` builds once, pushes an immutable version and deploys its digest to dev.
4. The manual workflow promotes the exact dev digest to production without rebuilding.
5. Readiness and sample smoke checks validate both environments.
6. A failed production validation can restore the prior digest.
7. Dev/Grafana authentication, no-public-SSH, and private-OTLP controls are verified.

### 20.3 Phase 4C is complete when

1. Dev and production emit metrics, logs and traces with correct service, environment and version.
2. The dashboard filters correctly by environment and version.
3. Panel links reach correlated logs/traces.
4. Seven-day retention and storage limits are configured.
5. The controlled failure fires the alert with every required annotation and sends it to the test webhook.
6. Recovery resolves the alert.
7. The evidence report is captured without secrets.
8. Every Phase 4-created AWS resource is deleted and teardown verification passes.

## 21. Release-Quality Definition of Done

A backlog item is complete only when all applicable elements exist:

- implementation;
- automated tests;
- configuration validation;
- security/privacy review;
- failure and cleanup behavior;
- documentation/runbook updates;
- CI evidence;
- demonstration evidence where required.

Feature code or a successful manual test alone is not complete.

## 22. Decision Record

| Area | Agreed decision |
| --- | --- |
| Phase goal | Production-grade portfolio deployment and observability exercise |
| Cloud lifetime | Destroy everything after demonstration |
| Public product mode | Synthetic sample only |
| Application data | Ephemeral; no durable AWS dataset storage |
| Image | One multi-stage Node-to-Python production image |
| Frontend serving | FastAPI serves compiled React assets |
| Compose | Base app Compose plus deployment override with Caddy |
| Integration tests | Eight critical container/system contracts |
| E2E | One Playwright journey across all analytics sections |
| Infrastructure | Foundation, dev, prod and observability CloudFormation stacks |
| Environments | Independent dev/prod EC2 resources using one reusable template |
| Ingress | Caddy HTTPS; dev and Grafana authenticated; prod public sample-only |
| Administration | Systems Manager; no public SSH |
| Registry | ECR with immutable readable tags |
| Release identity | Human tag plus digest-pinned deployment |
| CI/CD | PR tests; `main` to dev; manual approved dev-to-prod promotion |
| Rollback | Restore prior production digest on failed verification |
| AWS authentication | GitHub OIDC with separate least-privilege roles |
| Secrets | SSM Parameter Store `SecureString` |
| Health | Separate live and ready endpoints plus sample smoke check |
| Instrumentation | Backend auto-instrumentation plus domain spans |
| Resource attributes | `service.name`, `service.version`, `deployment.environment.name` |
| Trace sampling | 100%, environment-configurable |
| Observability | Collector, Prometheus, Loki, Tempo and Grafana |
| Retention | Seven days on bounded encrypted EBS |
| Dashboard | One OSA Operations dashboard with environment/version filters |
| Metrics | Focused HTTP, dataset, validation, analytics, DuckDB, runtime and Collector set |
| Alert | Three internal dataset-creation failures/10m, sustained 5m |
| Notification | Configurable test webhook |
| Delivery stages | 4A Container, 4B AWS Delivery, 4C Observability & Demonstration |

## 23. Primary Technical References

- [AI Shipping: Deploy a Full-Stack App with AI Coding Assistants](https://aishippingblog.com/p/deploy-a-full-stack-app-with-ai-coding)
- [AI Shipping: DevOps and Observability for an AI-Built App](https://aishippingblog.com/p/devops-and-observability-for-an-ai)
- [GitHub Docs: Configuring OpenID Connect in Amazon Web Services](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [AWS CloudFormation: AWS::ECR::Repository](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecr-repository.html)
- [AWS IAM: Configuring a role for GitHub OIDC](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)
- [OpenTelemetry service semantic conventions](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [OpenTelemetry deployment environment semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/deployment/)
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)

