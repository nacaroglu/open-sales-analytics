"""Offline security and routing contracts for the Grafana test webhook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_alert_webhook_config import validate_secret_file, validate_webhook_url  # noqa: E402

CONTACT_POINT = ROOT / "observability/provisioning/alerting/osa-test-webhook.json"
ALERT_RULE = ROOT / "observability/provisioning/alerting/osa-repeated-dataset-failures.json"
PREFLIGHT = ROOT / "scripts/validate_alert_webhook_config.py"
COMPOSE = ROOT / "observability/compose.yaml"
ENTRYPOINT = ROOT / "observability/grafana-entrypoint.sh"


class GrafanaWebhookContractTests(unittest.TestCase):
    def test_contact_point_has_stable_identity_and_reads_url_from_runtime_secret(self) -> None:
        config = json.loads(CONTACT_POINT.read_text(encoding="utf-8"))
        points = config["contactPoints"]
        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertEqual(point["name"], "OSA Test Webhook")
        self.assertEqual(len(point["receivers"]), 1)
        receiver = point["receivers"][0]
        self.assertEqual(receiver["uid"], "osa-test-webhook")
        self.assertEqual(receiver["type"], "webhook")
        self.assertEqual(receiver["settings"]["url"], "$OSA_ALERT_WEBHOOK_URL")
        self.assertEqual(receiver["settings"]["httpMethod"], "POST")
        self.assertEqual(receiver["settings"]["maxAlerts"], "10")
        self.assertFalse(receiver["disableResolveMessage"])
        self.assertFalse(
            {"username", "password", "authorization_credentials", "hmacConfig"}
            & set(receiver["settings"])
        )
        contact_text = CONTACT_POINT.read_text(encoding="utf-8")
        self.assertNotIn("https://", contact_text)
        self.assertNotIn("synthetic", contact_text)

    def test_only_repeated_dataset_creation_alert_routes_to_test_contact_point(self) -> None:
        config = json.loads(ALERT_RULE.read_text(encoding="utf-8"))
        rules = [rule for group in config["groups"] for rule in group["rules"]]
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule["title"], "OSARepeatedDatasetCreationFailures")
        self.assertEqual(rule["notification_settings"]["receiver"], "OSA Test Webhook")
        self.assertEqual(
            set(rule["notification_settings"]["group_by"]),
            {"alertname", "service", "environment", "deployed_version"},
        )
        contact_text = CONTACT_POINT.read_text(encoding="utf-8")
        self.assertNotIn("policies", contact_text)
        self.assertNotIn("notification_settings", contact_text)
        self.assertEqual(
            set(rule["labels"]),
            {"service", "environment", "deployed_version", "severity", "owner"},
        )
        self.assertEqual(
            set(rule["annotations"]),
            {"summary", "description", "dashboard_url", "runbook_url", "logs_and_traces"},
        )
        payload_contract = json.dumps(
            {"labels": rule["labels"], "annotations": rule["annotations"]}
        ).lower()
        for forbidden in (
            "dataset_id",
            "customer_id",
            "order_id",
            "token",
            "request_url",
            "request_body",
            "exception_message",
            "password",
        ):
            self.assertNotIn(forbidden, payload_contract)

    def test_compose_keeps_endpoint_out_of_container_metadata_and_reads_secret_file(self) -> None:
        compose_text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("OSA_ALERT_WEBHOOK_URL_FILE", compose_text)
        self.assertIn("osa_alert_webhook_url", compose_text)
        self.assertNotIn("OSA_ALERT_WEBHOOK_URL:", compose_text)
        entrypoint_text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("/run/secrets/osa_alert_webhook_url", entrypoint_text)
        self.assertIn("export OSA_ALERT_WEBHOOK_URL", entrypoint_text)
        self.assertIn("unset webhook_url", entrypoint_text)

    def test_missing_preflight_configuration_reports_action_without_echoing_values(self) -> None:
        marker = "PRIVATE_WEBHOOK_MARKER"
        environment = dict(os.environ)
        environment.pop("OSA_ALERT_WEBHOOK_URL_FILE", None)
        environment["UNUSED_WEBHOOK_MARKER"] = marker
        result = subprocess.run(
            [sys.executable, str(PREFLIGHT)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("OSA_ALERT_WEBHOOK_URL_FILE", result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_webhook_url_requires_https_without_leaking_invalid_values(self) -> None:
        self.assertIsNone(validate_webhook_url("https://hooks.receiver.example/secret-path"))
        self.assertIsNone(validate_webhook_url("https://hooks.receiver.example/send?key=synthetic"))
        marker = "PRIVATE_WEBHOOK_MARKER"
        for value in (
            f"http://hooks.receiver.example/{marker}",
            f"https://user:{marker}@hooks.receiver.example/path",
            "https://localhost/hook",
            "https://127.0.0.1/hook",
            "",
        ):
            with self.subTest(value=value):
                error = validate_webhook_url(value)
                self.assertIsNotNone(error)
                self.assertNotIn(marker, error or "")

    def test_secret_file_preflight_checks_permissions_location_and_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outside_path = Path(directory) / "webhook-url"
            outside_path.write_text(
                "https://hooks.receiver.example/test-secret\n", encoding="utf-8"
            )
            outside_path.chmod(0o400)
            self.assertIsNone(
                validate_secret_file(
                    str(outside_path), repository_root=ROOT, required_uid=os.getuid()
                )
            )

            writable_path = Path(directory) / "writable-url"
            writable_path.write_text("https://hooks.receiver.example/path", encoding="utf-8")
            writable_path.chmod(0o644)
            error = validate_secret_file(
                str(writable_path), repository_root=ROOT, required_uid=os.getuid()
            )
            self.assertIn("mode 0400", error or "")
            self.assertNotIn("hooks.receiver.example", error or "")

            inside_root = ROOT / ".test-webhook-url"
            try:
                inside_root.write_text("https://hooks.receiver.example/path", encoding="utf-8")
                inside_root.chmod(0o400)
                error = validate_secret_file(
                    str(inside_root), repository_root=ROOT, required_uid=os.getuid()
                )
                self.assertIn("outside the repository", error or "")
            finally:
                inside_root.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
