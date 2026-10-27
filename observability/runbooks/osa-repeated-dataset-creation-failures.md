# Runbook: OSARepeatedDatasetCreationFailures

**Runbook version:** 1  
**Owner:** `osa-maintainer`

## Meaning

One service, environment, and deployed version recorded at least three internal
dataset or sample creation failures in ten minutes. The condition stayed above
the threshold for five minutes. Invalid CSVs and documented validation
rejections are excluded by the alert query.

## First checks

1. Open the alert's OSA Operations dashboard link. Confirm the `service`,
   `environment`, and `deployed_version` labels. A value of `unknown` means the
   matching telemetry label was absent or failed its allowlist; inspect the
   resource identity configuration before relying on dashboard filters.
2. In the Dataset workflow row, compare internal creation failures with sample
   and upload outcomes. Check Prometheus targets and recent deployment status
   if there is no data.
3. Use the dashboard's Loki link with the same service/environment/version
   filters. Find the failure log, copy its `trace_id`, then open the correlated
   span in Tempo. The logs and spans contain no dataset IDs, customer data,
   bearer tokens, or request bodies; do not add those values to queries or
   incident notes.

## Recovery and escalation

Check recent changes to temporary storage, permissions, and dataset creation
dependencies. After the internal failure rate drops below three events in the
rolling ten-minute window, the alert query returns no qualifying series and
Grafana resolves the alert. If failures continue or the telemetry context is
missing, escalate to the OSA maintainer with the alert labels, deployment
version, and trace ID only.
