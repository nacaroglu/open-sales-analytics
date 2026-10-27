import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_dev_deployment.py"
SPEC = importlib.util.spec_from_file_location("verify_dev_deployment", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)

REGION = "eu-central-1"
HOST = "dev.example.com"
DIGEST = "a" * 64
VERSION = "20261027-133045-abcdef0"
DATASET_ID = "aBcDeFgHiJkLmN_0123456"
TOKEN = "T" * 43
USERNAME = "osa-smoke"
PASSWORD = "smoke-secret-marker"
CREDENTIAL = f"{USERNAME}:{PASSWORD}"
INPUTS = VERIFY.VerificationInputs(REGION, HOST, DIGEST, VERSION)
STACK_OUTPUTS = json.dumps(
    {
        "Stacks": [
            {
                "Outputs": [
                    {"OutputKey": "ImageDigest", "OutputValue": DIGEST},
                    {"OutputKey": "ReleaseVersion", "OutputValue": VERSION},
                ]
            }
        ]
    }
)
CREATED = {
    "dataset_id": DATASET_ID,
    "token": TOKEN,
    "meta": {
        "currency": "USD",
        "row_count": 14397,
        "date_range": {"min": "2024-01-01", "max": "2025-12-31"},
    },
    "warnings": [],
}
ANALYTICS = {
    "kpis": {"gross_sales": "675816.7000", "orders": 10000, "units_sold": 24380},
    "trend": [{"bucket_start": "2024-01-01", "gross_sales": "10.0000"}],
    "top_products": [{"product_id": "p1", "product_name": "Sample", "gross_sales": "5.0000"}],
}


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None


def aws_runner(
    *,
    credential: str = CREDENTIAL,
    stack_outputs: str = STACK_OUTPUTS,
    parameter_type: str = "SecureString",
):
    calls: list[list[str]] = []

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["aws", "cloudformation", "describe-stacks"]:
            return subprocess.CompletedProcess(command, 0, stdout=stack_outputs, stderr="")
        if command[:3] == ["aws", "ssm", "get-parameter"]:
            value = parameter_type if "Parameter.Type" in command else credential
            return subprocess.CompletedProcess(command, 0, stdout=value, stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected command")

    return run, calls


def http_sequence(*, fail_analytics: bool = False, fail_delete: bool = False):
    calls: list[tuple[str, str, dict[str, str], object]] = []

    def opener(request, *, timeout: float, context):
        method = request.get_method()
        headers = dict(request.header_items())
        body = request.data
        calls.append((method, request.full_url, headers, body))
        assert timeout > 0
        assert context.check_hostname is True
        assert context.verify_mode != 0
        if request.full_url.endswith("/health/ready"):
            return FakeResponse(
                200,
                json.dumps(
                    {
                        "status": "ready",
                        "environment": "development",
                        "version": VERSION,
                    }
                ).encode(),
            )
        if request.full_url.endswith("/api/datasets/sample"):
            return FakeResponse(201, json.dumps(CREATED).encode())
        if request.full_url.endswith("/analytics"):
            if fail_analytics:
                raise urllib.error.HTTPError(request.full_url, 500, "failed", {}, None)
            return FakeResponse(200, json.dumps(ANALYTICS).encode())
        if request.full_url.endswith(f"/api/datasets/{DATASET_ID}") and method == "DELETE":
            if fail_delete:
                return FakeResponse(500, b"")
            return FakeResponse(204, b"")
        raise AssertionError(f"Unexpected HTTP request: {method} {request.full_url}")

    return opener, calls


def test_read_smoke_credential_uses_only_secure_parameter_and_masks_it(capsys):
    runner, calls = aws_runner()

    username, password = VERIFY.read_smoke_credential(REGION, runner=runner)

    assert (username, password) == (USERNAME, PASSWORD)
    assert calls == [
        [
            "aws",
            "ssm",
            "get-parameter",
            "--name",
            "/osa/dev/caddy/smoke-credential",
            "--query",
            "Parameter.Type",
            "--output",
            "text",
            "--region",
            REGION,
        ],
        [
            "aws",
            "ssm",
            "get-parameter",
            "--name",
            "/osa/dev/caddy/smoke-credential",
            "--with-decryption",
            "--query",
            "Parameter.Value",
            "--output",
            "text",
            "--region",
            REGION,
        ],
    ]
    assert f"::add-mask::{CREDENTIAL}" in capsys.readouterr().out


def test_read_smoke_credential_rejects_plain_string_without_decrypting():
    runner, calls = aws_runner(parameter_type="String")

    with pytest.raises(VERIFY.VerificationError, match="must be a SecureString"):
        VERIFY.read_smoke_credential(REGION, runner=runner)

    assert len(calls) == 1
    assert "Parameter.Type" in calls[0]
    assert "--with-decryption" not in calls[0]


@pytest.mark.parametrize(
    "credential", ["", "username-only", ":password", "user:", "user:pass\nword"]
)
def test_read_smoke_credential_rejects_malformed_value(credential):
    runner, _ = aws_runner(credential=credential)
    with pytest.raises(VERIFY.VerificationError, match="credential is missing or malformed"):
        VERIFY.read_smoke_credential(REGION, runner=runner)


def test_published_digest_prefix_is_normalized_against_stack_output():
    VERIFY.verify_deployment(
        VERIFY.VerificationInputs(REGION, HOST, f"sha256:{DIGEST}", VERSION),
        runner=aws_runner()[0],
        opener=http_sequence()[0],
    )


def test_ssm_retrieval_failure_does_not_echo_aws_error_or_secret(capsys):
    calls = []

    def failed_runner(command, **kwargs):
        calls.append(command)
        if "Parameter.Type" in command:
            return subprocess.CompletedProcess(command, 0, stdout="SecureString", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=PASSWORD)

    with pytest.raises(VERIFY.VerificationError, match="retrieval failed") as error:
        VERIFY.read_smoke_credential(REGION, runner=failed_runner)
    assert len(calls) == 2
    assert "--with-decryption" not in calls[0]
    assert "--with-decryption" in calls[1]
    assert PASSWORD not in str(error.value)
    assert PASSWORD not in capsys.readouterr().out


def test_stack_metadata_is_read_only_and_must_match_expected_release():
    runner, calls = aws_runner()

    VERIFY.verify_deployment(
        INPUTS,
        runner=runner,
        opener=http_sequence()[0],
        summary_path=None,
    )

    assert calls[0][:5] == [
        "aws",
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        "osa-dev",
    ]
    assert calls[1][0:3] == ["aws", "ssm", "get-parameter"]
    assert not any(
        "update-stack" in value or "osa-prod" in value for call in calls for value in call
    )


def test_stack_metadata_mismatch_stops_before_reading_the_credential():
    wrong_outputs = json.dumps(
        {
            "Stacks": [
                {
                    "Outputs": [
                        {"OutputKey": "ImageDigest", "OutputValue": "b" * 64},
                        {"OutputKey": "ReleaseVersion", "OutputValue": VERSION},
                    ]
                }
            ]
        }
    )
    runner, calls = aws_runner(stack_outputs=wrong_outputs)

    with pytest.raises(VERIFY.VerificationError, match="does not match the published image"):
        VERIFY.verify_deployment(INPUTS, runner=runner, opener=http_sequence()[0])

    assert len(calls) == 1


def test_sample_workflow_authenticates_creation_then_uses_bearer_and_cleans_up():
    opener, calls = http_sequence()

    VERIFY.verify_sample_workflow(f"https://{HOST}", USERNAME, PASSWORD, opener=opener)

    assert [call[0] for call in calls] == ["POST", "GET", "DELETE"]
    assert calls[0][2]["Authorization"].startswith("Basic ")
    assert calls[1][2]["Authorization"] == f"Bearer {TOKEN}"
    assert calls[2][2]["Authorization"] == f"Bearer {TOKEN}"
    assert calls[0][1].endswith("/api/datasets/sample")
    assert calls[1][1].endswith(f"/api/datasets/{DATASET_ID}/analytics")
    assert calls[2][1].endswith(f"/api/datasets/{DATASET_ID}")


def test_sample_workflow_cleans_up_even_when_analytics_fails():
    opener, calls = http_sequence(fail_analytics=True)

    with pytest.raises(VERIFY.VerificationError, match="Sample analytics returned HTTP 500"):
        VERIFY.verify_sample_workflow(f"https://{HOST}", USERNAME, PASSWORD, opener=opener)

    assert [call[0] for call in calls] == ["POST", "GET", "DELETE"]


def test_sample_workflow_reports_cleanup_failure_after_analytics_failure():
    opener, calls = http_sequence(fail_analytics=True, fail_delete=True)

    with pytest.raises(VERIFY.VerificationError, match="cleanup also failed"):
        VERIFY.verify_sample_workflow(f"https://{HOST}", USERNAME, PASSWORD, opener=opener)

    assert calls[-1][0] == "DELETE"


def test_sample_workflow_rejects_unrepresentative_analytics_but_still_cleans_up():
    opener, calls = http_sequence()
    original = VERIFY._validate_analytics
    VERIFY._validate_analytics = lambda _: (_ for _ in ()).throw(
        VERIFY.VerificationError("Sample analytics KPIs do not match the bundled sample.")
    )
    try:
        with pytest.raises(VERIFY.VerificationError, match="do not match the bundled sample"):
            VERIFY.verify_sample_workflow(f"https://{HOST}", USERNAME, PASSWORD, opener=opener)
    finally:
        VERIFY._validate_analytics = original
    assert calls[-1][0] == "DELETE"


def test_readiness_requires_exact_environment_version_and_verified_https():
    opener, calls = http_sequence()

    VERIFY.wait_until_ready(f"https://{HOST}", USERNAME, PASSWORD, VERSION, opener=opener)

    assert calls[0][1] == f"https://{HOST}/health/ready"
    assert calls[0][2]["Authorization"].startswith("Basic ")


def test_readiness_version_mismatch_is_terminal():
    def opener(request, **_: Any):
        body = json.dumps(
            {
                "status": "ready",
                "environment": "development",
                "version": "wrong-version",
            }
        ).encode()
        return FakeResponse(200, body)

    with pytest.raises(VERIFY.VerificationError, match="metadata does not match"):
        VERIFY.wait_until_ready(f"https://{HOST}", USERNAME, PASSWORD, VERSION, opener=opener)


def test_readiness_timeout_is_bounded():
    now = [0.0]
    sleeps: list[float] = []

    def opener(request, **_: Any):
        raise urllib.error.URLError("temporary failure")

    def sleep(duration: float) -> None:
        sleeps.append(duration)
        now[0] += duration

    with pytest.raises(VERIFY.VerificationError, match="timed out"):
        VERIFY.wait_until_ready(
            f"https://{HOST}",
            USERNAME,
            PASSWORD,
            VERSION,
            timeout_seconds=3,
            opener=opener,
            monotonic=lambda: now[0],
            sleep=sleep,
        )
    assert sleeps and sum(sleeps) <= 3


def test_summary_contains_release_identity_and_no_secret_or_token(tmp_path: Path):
    summary = tmp_path / "summary.md"

    VERIFY.write_summary(
        summary,
        DIGEST,
        VERSION,
        readiness="PASS",
        smoke="PASS",
        cleanup="PASS",
        failure_stage=None,
    )

    content = summary.read_text(encoding="utf-8")
    assert "Environment: development" in content
    assert f"Image tag: `{VERSION}`" in content
    assert f"Release version: `{VERSION}`" in content
    assert DIGEST in content
    assert "CloudFormation deployment: PASS" in content
    assert "Readiness: PASS" in content
    assert "Sample analytics smoke: PASS" in content
    assert "Temporary sample cleanup: PASS" in content
    assert "Result: PASS" in content
    assert HOST not in content
    assert PASSWORD not in content
    assert TOKEN not in content


def test_failure_summary_identifies_stage_and_cleanup_without_infrastructure_values(tmp_path: Path):
    summary = tmp_path / "summary.md"

    VERIFY.write_summary(
        summary,
        DIGEST,
        VERSION,
        readiness="PASS",
        smoke="FAIL",
        cleanup="PASS",
        failure_stage="Sample analytics smoke",
    )

    content = summary.read_text(encoding="utf-8")
    assert "Sample analytics smoke: FAIL" in content
    assert "Failure stage: Sample analytics smoke" in content
    assert "Temporary sample cleanup: PASS" in content
    assert "Result: FAIL" in content
    for marker in (PASSWORD, TOKEN, CREDENTIAL, HOST, "10.0.0.5", "123456789012"):
        assert marker not in content


def test_verification_main_writes_failure_evidence_without_error_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    summary = tmp_path / "summary.md"
    for key, value in {
        "AWS_REGION": REGION,
        "OSA_DEV_HOSTNAME": HOST,
        "EXPECTED_IMAGE_DIGEST": DIGEST,
        "EXPECTED_RELEASE_VERSION": VERSION,
        "GITHUB_STEP_SUMMARY": str(summary),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["verify_dev_deployment.py"])

    def fail_verification(_inputs, *, summary_path):
        assert summary_path == summary
        raise VERIFY.VerificationError(
            "Development readiness timed out; credential-marker",
            stage="Development readiness",
        )

    monkeypatch.setattr(VERIFY, "verify_deployment", fail_verification)

    assert VERIFY.main() == 1
    assert "credential-marker" in capsys.readouterr().err
    content = summary.read_text(encoding="utf-8")
    assert "CloudFormation deployment: PASS" in content
    assert "Readiness: FAIL" in content
    assert "Sample analytics smoke: NOT RUN" in content
    assert "Temporary sample cleanup: NOT RUN" in content
    assert "Failure stage: Development readiness" in content
    for marker in ("credential-marker", HOST, "123456789012", TOKEN, PASSWORD):
        assert marker not in content


def test_input_validation_rejects_malformed_hostname_digest_and_version():
    for inputs in (
        VERIFY.VerificationInputs(REGION, "https://dev.example.com", DIGEST, VERSION),
        VERIFY.VerificationInputs(REGION, HOST, "not-a-digest", VERSION),
        VERIFY.VerificationInputs(REGION, HOST, DIGEST, "mutable-tag"),
    ):
        with pytest.raises(VERIFY.VerificationError):
            VERIFY.validate_inputs(inputs)
