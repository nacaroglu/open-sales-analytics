"""Offline contract tests for the provisioned repeated dataset failure alert."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_FILE = ROOT / "observability/provisioning/alerting/osa-repeated-dataset-failures.json"
FIXTURES = ROOT / "observability/fixtures/repeated-dataset-alert.json"
RUNBOOK = ROOT / "observability/runbooks/osa-repeated-dataset-creation-failures.md"
LABEL_FIXTURES = ROOT / "observability/fixtures/alert-label-values.json"


class GrafanaAlertContractTests(unittest.TestCase):
    def test_rule_counts_internal_failures_grouped_by_bounded_release_identity(self) -> None:
        config = json.loads(RULE_FILE.read_text(encoding="utf-8"))
        group = config["groups"][0]
        rule = group["rules"][0]
        self.assertEqual(rule["title"], "OSARepeatedDatasetCreationFailures")
        self.assertEqual(group["name"], "osa-reliability")
        self.assertEqual(rule["for"], "5m")
        self.assertEqual(rule["noDataState"], "OK")
        query = rule["data"][0]["model"]["expr"]
        self.assertIn("increase(osa_dataset_operations_total{", query)
        for selector in (
            'operation="create"',
            'outcome="failure"',
            'failure_class="internal"',
        ):
            self.assertIn(selector, query)
        self.assertNotIn('failure_class="validation"', query)
        self.assertIn("[10m]", query)
        grouping = re.search(r"sum by \(([^)]+)\)", query)
        self.assertIsNotNone(grouping)
        self.assertEqual(
            {label.strip() for label in grouping.group(1).split(",")},
            {"service_name", "deployment_environment_name", "service_version"},
        )
        for forbidden in ("dataset_id", "user_id", "filename", "request_id", "token"):
            self.assertNotIn(forbidden, query)
        self.assertRegex(query, r"\)\s*>=\s*3\s*$")

    def test_fixtures_cover_pending_firing_exclusion_and_resolution(self) -> None:
        fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
        config = json.loads(RULE_FILE.read_text(encoding="utf-8"))
        rule = config["groups"][0]["rules"][0]
        threshold = int(re.search(r">=\s*(\d+)", rule["data"][0]["model"]["expr"]).group(1))
        pending_seconds = int(rule["for"].removesuffix("m")) * 60
        self.assertEqual(
            {case["name"] for case in fixtures},
            {
                "below_threshold",
                "validation_rejections_excluded",
                "pending_before_five_minutes",
                "fires_after_five_minutes",
                "resolves_below_threshold",
            },
        )
        for case in fixtures:
            with self.subTest(case=case["name"]):
                count = case["internal_failures"]
                if case["name"] == "validation_rejections_excluded":
                    self.assertGreater(case["validation_rejections"], threshold)
                    self.assertEqual(count, 0)
                state = (
                    "Normal"
                    if count < threshold
                    else "Firing"
                    if case["sustained_for_seconds"] >= pending_seconds
                    else "Pending"
                )
                if case["name"] == "resolves_below_threshold":
                    self.assertEqual(case["previous_state"], "Firing")
                self.assertEqual(case["expected_state"], state)

    def test_alert_labels_and_annotations_have_safe_operator_context(self) -> None:
        config = json.loads(RULE_FILE.read_text(encoding="utf-8"))
        rule = config["groups"][0]["rules"][0]
        labels = rule["labels"]
        self.assertEqual(
            set(labels), {"service", "environment", "deployed_version", "severity", "owner"}
        )
        self.assertEqual(labels["severity"], "critical")
        self.assertEqual(labels["owner"], "osa-maintainer")
        for key, source in (
            ("service", "service_name"),
            ("environment", "deployment_environment_name"),
            ("deployed_version", "service_version"),
        ):
            self.assertIn(source, labels[key])
            self.assertIn("match", labels[key])
            self.assertIn("and $value", labels[key])
            self.assertIn("unknown", labels[key])

        annotations = rule["annotations"]
        self.assertIn("externalURL", annotations["dashboard_url"])
        self.assertIn('reReplaceAll "/+$" "" (externalURL)', annotations["dashboard_url"])
        self.assertIn("var-environment=", annotations["dashboard_url"])
        self.assertIn("var-deployed_version=", annotations["dashboard_url"])
        self.assertIn("match", annotations["dashboard_url"])
        self.assertIn("and $environment", annotations["dashboard_url"])
        self.assertIn("and $version", annotations["dashboard_url"])
        self.assertIn("unknown", annotations["dashboard_url"])
        self.assertIn("^(development|production)$", annotations["dashboard_url"])
        self.assertIn("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", annotations["dashboard_url"])
        self.assertIn("/d/osa-operations/osa-operations?", annotations["dashboard_url"])
        self.assertIn("github.com/nacaroglu/open-sales-analytics/blob/", annotations["runbook_url"])
        self.assertIn("Loki", annotations["logs_and_traces"])
        self.assertIn("Tempo", annotations["logs_and_traces"])
        for sensitive in ("dataset_id", "customer_id", "request_body", "bearer_token"):
            self.assertNotIn(sensitive, json.dumps(annotations).lower())
        self.assertTrue(RUNBOOK.is_file())
        runbook_text = RUNBOOK.read_text(encoding="utf-8").lower()
        self.assertIn("runbook version", runbook_text)
        self.assertIn("loki", runbook_text)
        self.assertIn("tempo", runbook_text)
        self.assertIn("trace_id", runbook_text)
        self.assertNotIn("dataset_id", runbook_text)
        self.assertNotIn("customer_id", runbook_text)

    def test_label_allowlists_turn_missing_or_untrusted_values_into_unknown(self) -> None:
        config = json.loads(RULE_FILE.read_text(encoding="utf-8"))
        labels = config["groups"][0]["rules"][0]["labels"]
        samples = json.loads(LABEL_FIXTURES.read_text(encoding="utf-8"))
        patterns = {
            "service": r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
            "environment": r"^(development|production)$",
            "deployed_version": r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
        }
        for label, pattern in patterns.items():
            self.assertIn(pattern, labels[label])
        for sample in samples:
            value = sample.get("label_value", "")
            self.assertEqual(
                value if re.fullmatch(patterns[sample["label_kind"]], value) else "unknown",
                sample["expected_safe_value"],
            )


if __name__ == "__main__":
    unittest.main()
