import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.deploy_dev_stack import (
    DeploymentError,
    DeploymentInputs,
    deploy_dev,
    inputs_from_environment,
)

REGION = "eu-central-1"
ROLE_ARN = "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-dev-deploy"
EXECUTION_ROLE_ARN = (
    "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-dev-application-execution"
)
REPOSITORY_URI = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/open-sales-analytics"
DIGEST = "a" * 64
IMAGE_REF = f"{REPOSITORY_URI}@sha256:{DIGEST}"
VERSION = "20261027-133045-abcdef0"


def valid_inputs(**overrides: str) -> DeploymentInputs:
    values = {
        "region": REGION,
        "deploy_role_arn": ROLE_ARN,
        "execution_role_arn": EXECUTION_ROLE_ARN,
        "repository_uri": REPOSITORY_URI,
        "image_ref": IMAGE_REF,
        "release_version": VERSION,
        "ami_id": "ami-0123456789abcdef0",
        "instance_type": "t3.small",
        "hostname": "dev.example.com",
    }
    values.update(overrides)
    return DeploymentInputs(**values)


def runner_for(*, fail_command: str | None = None):
    calls: list[list[str]] = []

    def run(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        calls.append(args)
        command_name = " ".join(
            args[:4] if args[:3] == ["aws", "cloudformation", "wait"] else args[:3]
        )
        status = 1 if fail_command == command_name else 0
        return subprocess.CompletedProcess(args, status, stdout="", stderr="credential-marker")

    return run, calls


def test_development_update_uses_exact_published_digest_and_waits_for_osa_dev(
    tmp_path: Path,
) -> None:
    runner, calls = runner_for()

    deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 2
    update = calls[0]
    assert update[:4] == ["aws", "cloudformation", "update-stack", "--stack-name"]
    assert update[4] == "osa-dev"
    assert update[update.index("--template-body") + 1].endswith(
        "deploy/cloudformation/osa-application.yaml"
    )
    assert update[update.index("--role-arn") + 1] == EXECUTION_ROLE_ARN
    assert update[update.index("--capabilities") + 1] == "CAPABILITY_NAMED_IAM"
    assert "ParameterKey=Environment,ParameterValue=development" in update
    assert f"ParameterKey=ImageDigest,ParameterValue={DIGEST}" in update
    assert f"ParameterKey=ReleaseVersion,ParameterValue={VERSION}" in update
    assert "ParameterKey=AmiId,ParameterValue=ami-0123456789abcdef0" in update
    assert "ParameterKey=InstanceType,ParameterValue=t3.small" in update
    assert "ParameterKey=PublicHostname,ParameterValue=dev.example.com" in update
    assert IMAGE_REF not in " ".join(update)
    assert calls[1] == [
        "aws",
        "cloudformation",
        "wait",
        "stack-update-complete",
        "--stack-name",
        "osa-dev",
        "--region",
        REGION,
    ]
    assert not any(
        "osa-prod" in value or "osa-observability" in value for cmd in calls for value in cmd
    )


@pytest.mark.parametrize(
    ("overrides", "stack_name"),
    [
        ({}, "osa-prod"),
        (
            {
                "deploy_role_arn": "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-prod-promotion"
            },
            "osa-dev",
        ),
        (
            {
                "execution_role_arn": "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-prod-application-execution"
            },
            "osa-dev",
        ),
        (
            {"image_ref": "123456789012.dkr.ecr.eu-central-1.amazonaws.com/other@sha256:" + DIGEST},
            "osa-dev",
        ),
        ({"image_ref": f"{REPOSITORY_URI}:20261027-133045-abcdef0"}, "osa-dev"),
    ],
)
def test_wrong_stack_role_or_image_fails_before_aws(
    overrides: dict[str, str], stack_name: str
) -> None:
    runner, calls = runner_for()

    with pytest.raises(DeploymentError):
        deploy_dev(valid_inputs(**overrides), runner=runner, stack_name=stack_name)

    assert calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"region": ""},
        {"deploy_role_arn": ""},
        {"execution_role_arn": ""},
        {"image_ref": ""},
        {"release_version": ""},
        {"ami_id": "not-an-ami"},
        {"instance_type": "invalid"},
        {"hostname": "dev..example.com"},
    ],
)
def test_missing_or_malformed_configuration_fails_before_aws(overrides: dict[str, str]) -> None:
    runner, calls = runner_for()

    with pytest.raises(DeploymentError):
        deploy_dev(valid_inputs(**overrides), runner=runner)

    assert calls == []


def test_missing_environment_configuration_is_rejected_without_mutation() -> None:
    assert inputs_from_environment({}).region == ""
    runner, calls = runner_for()

    with pytest.raises(DeploymentError):
        deploy_dev(inputs_from_environment({}), runner=runner)

    assert calls == []


def test_failed_stack_update_does_not_wait_or_proceed(tmp_path: Path) -> None:
    runner, calls = runner_for(fail_command="aws cloudformation update-stack")

    with pytest.raises(DeploymentError, match="osa-dev CloudFormation update failed") as error:
        deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 1
    assert "credential-marker" not in str(error.value)


def test_failed_stack_wait_reports_failure_and_stops(tmp_path: Path) -> None:
    runner, calls = runner_for(fail_command="aws cloudformation wait stack-update-complete")

    with pytest.raises(DeploymentError, match="osa-dev CloudFormation update wait failed"):
        deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 2


def test_dev_manifest_cannot_be_replaced_with_production_configuration(tmp_path: Path) -> None:
    bad_manifest = tmp_path / "osa-dev.json"
    data = json.loads(Path("deploy/cloudformation/environments/osa-dev.json").read_text())
    data["StackName"] = "osa-prod"
    bad_manifest.write_text(json.dumps(data), encoding="utf-8")
    runner, calls = runner_for()

    with pytest.raises(DeploymentError, match="Development manifest"):
        deploy_dev(valid_inputs(), runner=runner, manifest_path=bad_manifest)

    assert calls == []
