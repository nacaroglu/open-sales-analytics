# Phase 4 release evidence report

Overall status: Incomplete — live deployment, alert, rollback, stack, and teardown evidence remains pending. This report does not claim a complete Phase 4 demonstration.

Report reviewed at (UTC): `2026-10-28T04:41:09Z`

Each entry distinguishes automated checks from live evidence. A Pending entry records why the evidence is absent and the operator action needed to capture it. Replace Pending only after the linked artifact exists and has been reviewed for sensitive information.

## 1. Successful PR CI jobs

Evidence status: Complete
Source: [PR #332 CI run #40632249035](https://github.com/nacaroglu/open-sales-analytics/actions/runs/40632249035)
Evidence captured at (UTC): `2026-10-28T04:29:09Z`
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: GitHub Actions CI
Release/version: Commit `4c712392090427c73d704ca745e63048808af4c8` (PR #332 head; not a deployed release)
Evidence type: Automated

The run completed successfully, including backend, frontend, container/browser, Compose integration, telemetry resource identity, and offline infrastructure checks. This is CI evidence only; it is not evidence of a deployed release.

## 2. Immutable ECR tag and image digest

Evidence status: Pending — no immutable ECR tag and digest for a Phase 4 release have been captured in an approved artifact.
Source: [Deployment and image-publishing evidence issue #252](https://github.com/nacaroglu/open-sales-analytics/issues/252)
Evidence captured at (UTC): Pending — capture after the release image is published.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: AWS ECR
Release/version: Pending — no release digest is recorded.
Evidence type: Automated
Operator action: After #252's publishing workflow runs for the release, link its successful run and record the immutable tag and digest in an approved artifact.

## 3. Development deployment readiness and smoke results

Evidence status: Pending — no live development deployment readiness or sample-workflow smoke result is attached.
Source: [Development deployment evidence issue #252](https://github.com/nacaroglu/open-sales-analytics/issues/252)
Evidence captured at (UTC): Pending — capture after development deployment verification.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: Development
Release/version: Pending — record the deployed image digest and release version.
Evidence type: Live
Operator action: After the candidate digest is deployed, link the readiness and smoke workflow results and record the release identity.

## 4. Production promotion using the same digest

Evidence status: Pending — a protected production promotion using the development digest has not been captured.
Source: [Promotion evidence issue #252](https://github.com/nacaroglu/open-sales-analytics/issues/252)
Evidence captured at (UTC): Pending — capture after the protected promotion and production verification.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: Production
Release/version: Pending — confirm it is the same digest recorded in entries 2 and 3.
Evidence type: Live
Operator action: After development verification, run the approved production promotion and link evidence that identifies the same digest without exposing account or secret data.

## 5. Development and production application pages

Evidence status: Pending — sanitized application-page captures for both environments are not available.
Source: [Deployment and page evidence issue #252](https://github.com/nacaroglu/open-sales-analytics/issues/252)
Evidence captured at (UTC): Pending — capture after both application pages are verified.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: Development and production
Release/version: Pending — record the version shown by each environment.
Evidence type: Live
Operator action: Capture sanitized screenshots or approved artifact links for the development and production pages, with UTC timestamps and release context.

## 6. Grafana views filtered by environment and version

Evidence status: Pending — filtered dashboard captures for development and production have not been attached.
Source: [OSA Operations dashboard issue #261](https://github.com/nacaroglu/open-sales-analytics/issues/261)
Evidence captured at (UTC): Pending — capture after the dashboard has data for each environment and release.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: Development and production
Release/version: Pending — use the version selected in each dashboard view.
Evidence type: Live
Operator action: Capture sanitized dashboard views with both environment and version filters visible, and link the approved artifacts.

## 7. Trace connected to correlated logs

Evidence status: Pending — no sanitized trace-and-log correlation artifact from a deployed release has been captured.
Source: [Telemetry privacy and sampling issue #258](https://github.com/nacaroglu/open-sales-analytics/issues/258)
Evidence captured at (UTC): Pending — capture after trace and log export is verified in the deployed observability stack.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: Development or production
Release/version: Pending — record the deployed release identity.
Evidence type: Live
Operator action: Select a safe representative request, capture its trace and matching logs, and redact tokens, private addresses, and business identifiers before linking the artifact.

## 8. Controlled failures and firing/resolved alert

Evidence status: Pending — the development-only demonstration and firing/resolved alert evidence have not been run or captured.
Source: [Alert demonstration issue #269](https://github.com/nacaroglu/open-sales-analytics/issues/269)
Evidence captured at (UTC): Pending — capture only after an authorized development demonstration.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: Development only
Release/version: Pending — record the development release version and image digest before the demonstration.
Evidence type: Live
Operator action: When the #269 manual procedure is available and the development demonstration is authorized, run it, capture sanitized firing/resolved alert and webhook/dashboard/log/trace evidence, and confirm the normal sample workflow recovers.

## 9. Rollback demonstration or automated rollback test

Evidence status: Complete
Evidence note: The automated rollback test passed; no live production rollback was performed or is claimed.
Source: [PR #315](https://github.com/nacaroglu/open-sales-analytics/pull/315) and [successful CI run #40567977259](https://github.com/nacaroglu/open-sales-analytics/actions/runs/40567977259)
Evidence captured at (UTC): `2026-10-27T19:22:17Z`
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: GitHub Actions CI (automated rollback simulation)
Release/version: Commit `50a8f2b4954b16ff16136f8d2aaaded3704f52ef` (rollback workflow/test code; not a deployed release)
Evidence type: Automated

## 10. CloudFormation stack and resource summary

Evidence status: Pending — no sanitized summary of the deployed Phase 4 stacks and resources is available.
Source: [Observability infrastructure issue #263](https://github.com/nacaroglu/open-sales-analytics/issues/263)
Evidence captured at (UTC): Pending — capture after the required stacks are deployed and reviewed.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: AWS development, production, and observability stacks
Release/version: Pending — identify the release associated with the stack summary.
Evidence type: Live
Operator action: Capture an approved CloudFormation summary and redact account IDs, physical resource values, private addresses, and secret data before linking it.

## 11. Final cleanup commands and deletion verification

Evidence status: Pending — the guarded teardown and read-only deletion verification are not complete.
Source: [Guarded teardown issue #271](https://github.com/nacaroglu/open-sales-analytics/issues/271) and [resource-removal verification issue #272](https://github.com/nacaroglu/open-sales-analytics/issues/272)
Evidence captured at (UTC): Pending — capture after the approved teardown and verification finish.
Status checked at (UTC): `2026-10-28T04:41:09Z`
Environment: AWS temporary Phase 4 environment
Release/version: Pending — record the final deployed release identifier before teardown.
Evidence type: Live
Operator action: After #271 and #272 are implemented and reviewed, run the approval-gated teardown and read-only verifier; link sanitized commands and successful deletion results.

### Updating this report

- Keep all 11 numbered entries and their source, evidence capture timestamp, status-check timestamp, environment, release/version, and evidence-type fields.
- Use `Pending — <reason>` while evidence is missing, set the evidence capture time to Pending, and state a concrete operator action. Pending is never a successful demonstration.
- Change an entry to `Complete` only after its source artifact exists, its capture time is recorded in UTC, and another operator has reviewed it for sensitive data.
- Store sanitized screenshots under `_docs/images/phase-4/` or link an approved release artifact. Do not include account IDs, credentials, tokens, authentication data, private addresses, or unrelated dataset/business identifiers.
- Run `python3 scripts/validate_phase4_release_report.py` after every edit. The offline validator checks the entry contract and sensitive-value patterns; it does not contact AWS or verify live services.
