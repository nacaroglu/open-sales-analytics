# Phase 4 resource absence verification

After the operator completes the reviewed teardown in #271, run the verifier with
the AWS CLI configured for the intended account and region:

```sh
AWS_REGION=us-east-1 python3 scripts/verify_phase4_resource_absence.py
```

The command is read-only and makes no change or delete calls. It checks the
`osa-dev`, `osa-prod`, `osa-observability`, and `osa-foundation` CloudFormation
stacks, then looks for Phase 4 ownership markers in EC2 instances, EBS volumes
and snapshots, Elastic IPs, ECR, SSM parameters, and IAM roles. EC2 resources,
ECR, SSM, and IAM are scoped by the `Project=open-sales-analytics` and
`OSAStack=<stack>` tags used by the templates. IAM roles are further restricted
to the matching `/osa-<stack>/` path. ECR is restricted to the configured
foundation repository (`open-sales-analytics` by default).

The templates do not create Route 53 record sets: application and Grafana
hostnames are operator-supplied parameters and DNS remains externally managed.
Accordingly the Route 53 category is reported with zero in-scope records; the
verifier deliberately does not enumerate or inspect operator-owned hosted
zones. The SSM check covers only tagged stack-created parameters, not unrelated
runtime secrets such as `/osa/dev/caddy/auth`.

The report includes the UTC verification time, selected region, target stack
names, the stack names whose CloudFormation absence queries returned valid
results, resource categories, and a PASS result. A nonzero exit produces a
sanitized FAIL report with the same target list and only the stack names and
resource categories successfully checked before failure (empty when input
validation fails before any AWS query). Access denial, throttling, malformed or incomplete data,
and pagination errors fail immediately. Leftover resources are polled for up to
120 seconds by default; a timeout identifies only the resource categories still
present. No resource identifiers, account IDs, private IPs, credentials, or raw
AWS responses are printed. Adjust the bounded wait with
`--timeout-seconds` and `--poll-seconds` if teardown propagation needs more time.

The CI check is offline and uses mocked AWS CLI calls. Live AWS verification is
an operator-only post-teardown activity and is never run by CI.
