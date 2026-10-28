# Alert demonstration runbook (#269)

**Status: Pending live development demonstration.** This document and its validator are offline-only. They never contact AWS, Grafana, the app, or a webhook, and do not trigger failures.

## Scope and safety

Run manually, only against the authenticated development deployment. Never run against production or from ordinary CI. The demonstration is an operator-run procedure. Stop if any preflight, delivery, recovery, or resolution check fails. Do not retry the controlled-failure command to increase the alert count.

The controlled command from #268 must be invoked inside the app container through the authenticated SSM session and development Compose project. After #268 is merged and deployed, verify the command against that implementation. Its expected invocation is:

```sh
docker compose exec -T app env OSA_ENVIRONMENT=development PYTHONPATH=/app/backend \
  python -m app.controlled_failure --confirm-controlled-failure
```

This instruction is documentation only. It is not run by this document, the validator, tests, or CI.

## Preconditions

Record the following in the evidence file without copying credentials or private infrastructure identifiers:

- [ ] An approved, authenticated development-only operator session is active.
- [ ] Development app readiness and sample workflow are healthy.
- [ ] Observability services and the development telemetry route are healthy.
- [ ] `OSARepeatedDatasetCreationFailures` is provisioned with a 10-minute query window and 5-minute pending period.
- [ ] The configured test webhook contact point is healthy and selected by the alert.
- [ ] No matching alert is pending or firing.
- [ ] Development release version and image digest are recorded.
- [ ] Temporary-storage and dataset state are clean before starting.
- [ ] The #268 utility is present in the deployed app image and the command above has been verified.

Stop before generating failures if any check fails or is unknown.

## Procedure

1. Record preflight results and the release version/digest in `_docs/evidence/alert-demo-269.md`.
2. Start a UTC timestamp for the demonstration. Invoke the #268 CLI once inside the app container. It makes exactly three internal creation failures, using isolated temporary storage.
3. Verify the failures are classified as internal creation failures, not validation rejections. Confirm no dataset or temporary artifact remains. Do not inspect or copy unrelated customer/business data.
4. Observe Grafana for the configured 5-minute pending period. Confirm the alert is firing for development and the recorded release. Confirm the configured test webhook delivered the notification.
5. Capture sanitized alert state, bounded webhook labels, the dashboard filtered to development/release, and correlated logs and trace. Redact account identifiers, secrets, tokens, authentication data, private addresses, and unrelated dataset/business identifiers before retaining any evidence.
6. Stop generating failures. Check app readiness and the sample workflow. Confirm temporary storage is clean.
7. After all failures have aged out of the 10-minute query window, poll alert state at bounded intervals (at most 15 minutes total) until it is resolved. Confirm no matching alert remains pending or firing.
8. Record each observation in the evidence file. Use `Pending` until actually observed; do not infer success from configuration or offline tests.
9. Retain the sanitized evidence for issue #270.

If alert firing, webhook delivery, application recovery, or resolution fails, stop immediately; do not run another batch. Record the sanitized outcome and whether development health was restored. If health cannot be restored, report that clearly and follow the normal development recovery procedure.

## Expected timing

The rule counts at least three internal failures over 10 minutes and has a 5-minute pending period. Resolution is expected only after the failures age out of the query window and the pending/resolved evaluation completes. Use bounded polling; never use an unbounded wait.

## Evidence handling

Use the companion evidence template. Store only redacted screenshots/exports or concise observations in an approved repository location. Do not commit raw webhook payloads, screenshots containing private addresses, authentication material, or unrelated business identifiers. The template stays Pending until an operator performs the live run.
