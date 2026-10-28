import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "promote_production.py"
REPOSITORY_ROOT = SCRIPT.parents[1]
SCRIPTS_DIR = SCRIPT.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location("promote_production", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROMOTION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROMOTION
SPEC.loader.exec_module(PROMOTION)

REGION = "eu-central-1"
REPOSITORY = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/open-sales-analytics"
DEV_ROLE = "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-production-source-read"
PROD_ROLE = "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-prod-promotion"
EXEC_ROLE = (
    "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-prod-application-execution"
)
DIGEST = "a" * 64
OLD_DIGEST = "b" * 64
VERSION = "20261027-133045-abcdef0"
OLD_VERSION = "20261026-133045-abcdef0"


def config(**overrides: str):
    values = {
        "region": REGION,
        "repository": REPOSITORY,
        "source_read_role": DEV_ROLE,
        "promotion_role": PROD_ROLE,
        "execution_role": EXEC_ROLE,
        "ami": "ami-0123456789abcdef0",
        "instance_type": "t3.small",
        "hostname": "sales.example.com",
    }
    values.update(overrides)
    return PROMOTION.Config(**values)


def describe_json(stack: str, digest: str, version: str) -> str:
    return json.dumps(
        {
            "Stacks": [
                {
                    "StackName": stack,
                    "StackStatus": "UPDATE_COMPLETE",
                    "Outputs": [
                        {
                            "OutputKey": "ImageReference",
                            "OutputValue": f"{REPOSITORY}@sha256:{digest}",
                        },
                        {"OutputKey": "ReleaseVersion", "OutputValue": version},
                    ],
                }
            ]
        }
    )


def preflight_stdout(args: list[str]) -> str | None:
    if args[:3] == ["aws", "cloudformation", "describe-stacks"]:
        stack = args[args.index("--stack-name") + 1]
        if stack == "osa-observability":
            return "http://10.40.1.25:4318"
    if args[:3] == ["aws", "ssm", "get-parameter"]:
        return "SecureString"
    return None


def test_dev_metadata_is_parsed_and_bound_to_expected_ecr_repository():
    release = PROMOTION.parse_release(
        describe_json("osa-dev", DIGEST, VERSION), "osa-dev", REPOSITORY
    )

    assert release == PROMOTION.Release(DIGEST, VERSION)


@pytest.mark.parametrize(
    ("payload", "repository"),
    [
        ("{}", REPOSITORY),
        (describe_json("osa-prod", DIGEST, VERSION), REPOSITORY),
        (describe_json("osa-dev", "short", VERSION), REPOSITORY),
        (describe_json("osa-dev", DIGEST, "latest"), REPOSITORY),
        (
            describe_json("osa-dev", DIGEST, VERSION),
            "123456789012.dkr.ecr.eu-central-1.amazonaws.com/other",
        ),
        (
            json.dumps(
                {
                    "Stacks": [
                        {"StackName": "osa-dev", "StackStatus": "UPDATE_IN_PROGRESS", "Outputs": []}
                    ]
                }
            ),
            REPOSITORY,
        ),
    ],
)
def test_missing_or_malformed_dev_metadata_is_rejected(payload: str, repository: str):
    with pytest.raises(PROMOTION.PromotionError):
        PROMOTION.parse_release(payload, "osa-dev", repository)


def test_promotion_uses_only_the_dev_digest_and_never_builds_pushes_or_retags(tmp_path: Path):
    commands: list[list[str]] = []
    current = PROMOTION.Release(OLD_DIGEST, OLD_VERSION)

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal current
        args = list(command)
        commands.append(args)
        preflight = preflight_stdout(args)
        if preflight is not None:
            return subprocess.CompletedProcess(args, 0, stdout=preflight)
        if args[:3] == ["aws", "cloudformation", "describe-stacks"]:
            return subprocess.CompletedProcess(
                args, 0, stdout=describe_json("osa-prod", current.digest, current.version)
            )
        if args[:3] == ["aws", "cloudformation", "update-stack"]:
            digest = next(
                item.split(",ParameterValue=", 1)[1]
                for item in args
                if item.startswith("ParameterKey=ImageDigest,")
            )
            version = next(
                item.split(",ParameterValue=", 1)[1]
                for item in args
                if item.startswith("ParameterKey=ReleaseVersion,")
            )
            current = PROMOTION.Release(digest, version)
        return subprocess.CompletedProcess(args, 0, stdout="")

    summary = tmp_path / "summary.md"
    source = PROMOTION.Release(DIGEST, VERSION)
    previous = PROMOTION.promote(
        config(),
        source,
        runner=runner,
        env={"GITHUB_STEP_SUMMARY": str(summary)},
        verifier=lambda _config, _release: None,
    )

    assert previous == PROMOTION.Release(OLD_DIGEST, OLD_VERSION)
    update = next(
        command for command in commands if command[:3] == ["aws", "cloudformation", "update-stack"]
    )
    assert update[update.index("--stack-name") + 1] == "osa-prod"
    assert f"ParameterKey=ImageDigest,ParameterValue={DIGEST}" in update
    assert f"ParameterKey=ReleaseVersion,ParameterValue={VERSION}" in update
    assert not any(
        any(
            word in " ".join(command).lower()
            for word in ("docker", "build", "push", "retag", "aws ecr")
        )
        for command in commands
    )
    contents = summary.read_text(encoding="utf-8")
    assert (
        DIGEST in contents
        and VERSION in contents
        and OLD_DIGEST in contents
        and OLD_VERSION in contents
    )
    assert "Production verification: PASS" in contents
    assert "Environment: production" in contents
    assert f"Image tag: `{VERSION}`" in contents
    assert "Readiness: PASS" in contents
    assert "Sample analytics smoke: PASS" in contents
    assert "Rollback: not required" in contents
    for marker in ("123456789012", "sales.example.com", "password-marker", "token-marker"):
        assert marker not in contents


def test_failed_production_verification_restores_and_verifies_previous_release(tmp_path: Path):
    current = PROMOTION.Release(OLD_DIGEST, OLD_VERSION)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal current
        args = list(command)
        commands.append(args)
        preflight = preflight_stdout(args)
        if preflight is not None:
            return subprocess.CompletedProcess(args, 0, stdout=preflight)
        if args[:3] == ["aws", "cloudformation", "describe-stacks"]:
            return subprocess.CompletedProcess(
                args, 0, stdout=describe_json("osa-prod", current.digest, current.version)
            )
        if args[:3] == ["aws", "cloudformation", "update-stack"]:
            digest = next(
                item.split(",ParameterValue=", 1)[1]
                for item in args
                if item.startswith("ParameterKey=ImageDigest,")
            )
            version = next(
                item.split(",ParameterValue=", 1)[1]
                for item in args
                if item.startswith("ParameterKey=ReleaseVersion,")
            )
            current = PROMOTION.Release(digest, version)
        return subprocess.CompletedProcess(args, 0, stdout="")

    verified: list[PROMOTION.Release] = []

    def verifier(_config, release):
        verified.append(release)
        if release.digest == DIGEST:
            raise PROMOTION.PromotionError("Production sample analytics verification failed.")

    summary = tmp_path / "summary.md"
    with pytest.raises(PROMOTION.PromotionError, match="restored and verified"):
        PROMOTION.promote(
            config(),
            PROMOTION.Release(DIGEST, VERSION),
            runner=runner,
            verifier=verifier,
            env={"GITHUB_STEP_SUMMARY": str(summary)},
        )

    updates = [
        command for command in commands if command[:3] == ["aws", "cloudformation", "update-stack"]
    ]
    assert len(updates) == 2
    assert f"ParameterKey=ImageDigest,ParameterValue={OLD_DIGEST}" in updates[1]
    assert f"ParameterKey=ReleaseVersion,ParameterValue={OLD_VERSION}" in updates[1]
    assert current == PROMOTION.Release(OLD_DIGEST, OLD_VERSION)
    assert verified == [
        PROMOTION.Release(DIGEST, VERSION),
        PROMOTION.Release(OLD_DIGEST, OLD_VERSION),
    ]
    contents = summary.read_text(encoding="utf-8")
    assert "Production verification: FAIL" in contents
    assert "Readiness: PASS" in contents
    assert "Sample analytics smoke: FAIL" in contents
    assert "Failure stage: Sample analytics smoke" in contents
    assert "Rollback: PASS" in contents
    assert OLD_DIGEST in contents and DIGEST in contents


def test_failed_rollback_verification_is_reported_as_rollback_failure(tmp_path: Path):
    current = PROMOTION.Release(OLD_DIGEST, OLD_VERSION)

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal current
        args = list(command)
        preflight = preflight_stdout(args)
        if preflight is not None:
            return subprocess.CompletedProcess(args, 0, stdout=preflight)
        if args[:3] == ["aws", "cloudformation", "describe-stacks"]:
            return subprocess.CompletedProcess(
                args, 0, stdout=describe_json("osa-prod", current.digest, current.version)
            )
        if args[:3] == ["aws", "cloudformation", "update-stack"]:
            digest = next(
                item.split(",ParameterValue=", 1)[1]
                for item in args
                if item.startswith("ParameterKey=ImageDigest,")
            )
            version = next(
                item.split(",ParameterValue=", 1)[1]
                for item in args
                if item.startswith("ParameterKey=ReleaseVersion,")
            )
            current = PROMOTION.Release(digest, version)
        return subprocess.CompletedProcess(args, 0, stdout="")

    def verifier(_config, _release):
        raise PROMOTION.PromotionError("Production readiness verification failed.")

    summary = tmp_path / "summary.md"
    with pytest.raises(PROMOTION.PromotionError, match="rollback failed"):
        PROMOTION.promote(
            config(),
            PROMOTION.Release(DIGEST, VERSION),
            runner=runner,
            verifier=verifier,
            env={"GITHUB_STEP_SUMMARY": str(summary)},
        )

    assert current == PROMOTION.Release(OLD_DIGEST, OLD_VERSION)
    assert "Rollback: FAILED" in summary.read_text(encoding="utf-8")
    failure_summary = summary.read_text(encoding="utf-8")
    assert "Failure stage: Production readiness" in failure_summary
    assert "Readiness: FAIL" in failure_summary
    assert "Sample analytics smoke: NOT RUN" in failure_summary


def test_invalid_previous_production_release_stops_before_update():
    commands: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        commands.append(args)
        preflight = preflight_stdout(args)
        if preflight is not None:
            return subprocess.CompletedProcess(args, 0, stdout=preflight)
        return subprocess.CompletedProcess(args, 0, stdout="{}")

    with pytest.raises(PROMOTION.PromotionError, match="osa-prod release metadata"):
        PROMOTION.promote(
            config(),
            PROMOTION.Release(DIGEST, VERSION),
            runner=runner,
            verifier=lambda _config, _release: None,
            env={},
        )

    assert len(commands) == 3
    assert commands[0][0:3] == ["aws", "cloudformation", "describe-stacks"]
    assert "osa-observability" in commands[0]
    assert commands[1][:3] == ["aws", "ssm", "get-parameter"]
    assert commands[2][:3] == ["aws", "cloudformation", "describe-stacks"]


def test_invalid_previous_release_is_reported_without_attempting_an_update(tmp_path: Path):
    commands: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        commands.append(args)
        preflight = preflight_stdout(args)
        if preflight is not None:
            return subprocess.CompletedProcess(args, 0, stdout=preflight)
        return subprocess.CompletedProcess(args, 0, stdout="{}")

    summary = tmp_path / "summary.md"
    with pytest.raises(PROMOTION.PromotionError, match="osa-prod release metadata"):
        PROMOTION.promote(
            config(),
            PROMOTION.Release(DIGEST, VERSION),
            runner=runner,
            env={"GITHUB_STEP_SUMMARY": str(summary)},
            verifier=lambda _config, _release: None,
        )

    assert len(commands) == 3
    assert commands[0][0:3] == ["aws", "cloudformation", "describe-stacks"]
    assert "osa-observability" in commands[0]
    assert commands[1][:3] == ["aws", "ssm", "get-parameter"]
    assert commands[2][:3] == ["aws", "cloudformation", "describe-stacks"]
    content = summary.read_text(encoding="utf-8")
    assert "Previous production digest: `unavailable`" in content
    assert "Failure stage: Prior production metadata lookup" in content
    assert "Rollback: NOT RUN" in content
    assert "Result: FAIL" in content


def test_production_verifier_checks_readiness_sample_analytics_and_cleanup(capsys):
    dataset_id = "A" * 22
    token = "secret-smoke-token"
    responses = [
        (200, {"status": "ready", "environment": "production", "version": OLD_VERSION}),
        (200, {"status": "ready", "environment": "production", "version": VERSION}),
        (
            201,
            {
                "dataset_id": dataset_id,
                "token": token,
                "meta": {
                    "currency": "USD",
                    "date_range": PROMOTION.EXPECTED_SAMPLE_DATES,
                    "row_count": PROMOTION.EXPECTED_SAMPLE_ROWS,
                },
                "warnings": [],
            },
        ),
        (
            200,
            {
                "kpis": PROMOTION.EXPECTED_SAMPLE,
                "trend": [{"date": "2024-01-01"}],
                "top_products": [{"product_id": "p1"}],
            },
        ),
        (204, None),
    ]
    requests = []

    class Response:
        def __init__(self, status: int, body: dict | None):
            self.status = status
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"" if self.body is None else json.dumps(self.body).encode()

    def opener(request, **_kwargs):
        requests.append(request)
        status, body = responses.pop(0)
        return Response(status, body)

    PROMOTION.verify_production(
        config(),
        PROMOTION.Release(DIGEST, VERSION),
        opener=opener,
        timeout_seconds=1,
        sleep=lambda _duration: None,
    )

    assert [request.method for request in requests] == ["GET", "GET", "POST", "GET", "DELETE"]
    assert requests[0].full_url == "https://sales.example.com/health/ready"
    assert requests[2].full_url == "https://sales.example.com/api/datasets/sample"
    assert requests[2].get_header("Authorization") is None
    assert requests[3].get_header("Authorization") == f"Bearer {token}"
    assert requests[4].get_header("Authorization") == f"Bearer {token}"
    assert token in capsys.readouterr().out


def test_failed_update_wait_polls_until_cloudformation_rollback_is_complete():
    statuses = ["UPDATE_ROLLBACK_IN_PROGRESS", "UPDATE_ROLLBACK_COMPLETE"]
    now = 0.0

    def monotonic() -> float:
        return now

    def sleep(duration: float) -> None:
        nonlocal now
        now += duration

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        assert args[:3] == ["aws", "cloudformation", "describe-stacks"]
        status = statuses.pop(0)
        payload = {"Stacks": [{"StackName": "osa-prod", "StackStatus": status}]}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload))

    PROMOTION.wait_for_stack_settlement(
        runner, config(), timeout_seconds=10, monotonic=monotonic, sleep=sleep
    )

    assert statuses == []
    assert now == 5.0


def test_invalid_source_release_fails_before_any_aws_command():
    def unexpected_runner(*_: object, **__: object):
        pytest.fail("AWS must not be called for malformed metadata")

    with pytest.raises(PROMOTION.PromotionError):
        PROMOTION.promote(
            config(), PROMOTION.Release("bad", "latest"), runner=unexpected_runner, env={}
        )


@pytest.mark.parametrize(
    "override",
    [
        {"source_read_role": ""},
        {"repository": "example.invalid/image"},
        {"promotion_role": "arn:aws:iam::123456789012:role/other"},
    ],
)
def test_invalid_static_configuration_is_rejected(override: dict[str, str]):
    with pytest.raises(PROMOTION.PromotionError):
        PROMOTION.validate_config(config(**override))
