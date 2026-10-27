"""Offline contract tests for the provisioned repeated dataset failure alert."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_FILE = ROOT / "observability/provisioning/alerting/osa-repeated-dataset-failures.json"
FIXTURES = ROOT / "observability/fixtures/repeated-dataset-alert.json"


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
        self.assertIn('increase(osa_dataset_operations_total{', query)
        for selector in (
            'operation="create"', 'outcome="failure"', 'failure_class="internal"',
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
            {"below_threshold", "validation_rejections_excluded", "pending_before_five_minutes",
             "fires_after_five_minutes", "resolves_below_threshold"},
        )
        for case in fixtures:
            with self.subTest(case=case["name"]):
                count = case["internal_failures"]
                if case["name"] == "validation_rejections_excluded":
                    self.assertGreater(case["validation_rejections"], threshold)
                    self.assertEqual(count, 0)
                state = (
                    "Normal" if count < threshold
                    else "Firing" if case["sustained_for_seconds"] >= pending_seconds
                    else "Pending"
                )
                if case["name"] == "resolves_below_threshold":
                    self.assertEqual(case["previous_state"], "Firing")
                self.assertEqual(case["expected_state"], state)


if __name__ == "__main__":
    unittest.main()
