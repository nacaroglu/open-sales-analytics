import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

DEPLOY_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy_dev_stack.py"
REPOSITORY_ROOT = DEPLOY_SCRIPT.parents[1]
SCRIPTS_DIR = DEPLOY_SCRIPT.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
DEPLOY_SPEC = importlib.util.spec_from_file_location("deploy_dev_stack", DEPLOY_SCRIPT)
assert DEPLOY_SPEC is not None and DEPLOY_SPEC.loader is not None
DEPLOYMENT = importlib.util.module_from_spec(DEPLOY_SPEC)
sys.modules[DEPLOY_SPEC.name] = DEPLOYMENT
DEPLOY_SPEC.loader.exec_module(DEPLOYMENT)
DeploymentError = DEPLOYMENT.DeploymentError
DeploymentInputs = DEPLOYMENT.DeploymentInputs
deploy_dev = DEPLOYMENT.deploy_dev
inputs_from_environment = DEPLOYMENT.inputs_from_environment
main = DEPLOYMENT.main
write_summary = DEPLOYMENT.write_summary

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
        stdout = ""
        if args[:3] == ["aws", "cloudformation", "describe-stacks"]:
            stdout = "http://10.40.1.25:4318"
        elif args[:3] == ["aws", "ssm", "get-parameter"]:
            stdout = "SecureString"
        return subprocess.CompletedProcess(args, status, stdout=stdout, stderr="credential-marker")

    return run, calls


def test_development_update_uses_exact_published_digest_and_waits_for_osa_dev(
    tmp_path: Path,
) -> None:
    runner, calls = runner_for()

    deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 4
    endpoint_check, token_type_check, update = calls[:3]
    assert endpoint_check[:5] == [
        "aws",
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        "osa-observability",
    ]
    assert "CollectorPrivateEndpoint" in " ".join(endpoint_check)
    assert endpoint_check[endpoint_check.index("--region") + 1] == REGION
    assert token_type_check[:5] == [
        "aws",
        "ssm",
        "get-parameter",
        "--name",
        "/osa/dev/observability/otlp-token",
    ]
    assert "Parameter.Type" in token_type_check
    assert "--with-decryption" not in token_type_check
    assert update[:4] == ["aws", "cloudformation", "update-stack", "--stack-name"]
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
    assert calls[3] == [
        "aws",
        "cloudformation",
        "wait",
        "stack-update-complete",
        "--stack-name",
        "osa-dev",
        "--region",
        REGION,
    ]
    assert not any("osa-prod" in value for cmd in calls for value in cmd)


def test_development_deployment_summary_records_safe_release_evidence(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"

    write_summary(
        summary,
        valid_inputs(),
        result="PASS",
        failure_stage=None,
    )

    content = summary.read_text(encoding="utf-8")
    assert "Environment: development" in content
    assert f"Image tag: `{VERSION}`" in content
    assert f"Release version: `{VERSION}`" in content
    assert f"Image digest: `sha256:{DIGEST}`" in content
    assert "CloudFormation deployment: PASS" in content
    assert "Readiness: PENDING" in content
    assert "Sample analytics smoke: PENDING" in content
    assert "Result: PASS" in content
    for marker in ("123456789012", "dev.example.com", "ami-0123456789abcdef0", ROLE_ARN):
        assert marker not in content


def test_failed_development_deployment_summary_names_stage_and_redacts_inputs(
    tmp_path: Path,
) -> None:
    summary = tmp_path / "summary.md"

    write_summary(
        summary,
        valid_inputs(),
        result="FAIL",
        failure_stage="CloudFormation update wait",
    )

    content = summary.read_text(encoding="utf-8")
    assert "CloudFormation deployment: FAIL" in content
    assert "Failure stage: CloudFormation update wait" in content
    assert "CloudFormation rollback: NOT VERIFIED" in content
    assert "Result: FAIL" in content
    for marker in ("123456789012", "dev.example.com", ROLE_ARN, "credential-marker"):
        assert marker not in content


def test_deployment_main_writes_failure_summary_without_echoing_error_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    for key, value in {
        "AWS_REGION": REGION,
        "DEV_DEPLOY_ROLE_ARN": ROLE_ARN,
        "DEV_EXECUTION_ROLE_ARN": EXECUTION_ROLE_ARN,
        "ECR_REPOSITORY_URI": REPOSITORY_URI,
        "IMAGE_REF": IMAGE_REF,
        "RELEASE_VERSION": VERSION,
        "OSA_AMI_ID": "ami-0123456789abcdef0",
        "OSA_INSTANCE_TYPE": "t3.small",
        "OSA_DEV_HOSTNAME": "dev.example.com",
        "GITHUB_STEP_SUMMARY": str(summary),
    }.items():
        monkeypatch.setenv(key, value)

    def fail_deployment(_inputs: DeploymentInputs) -> None:
        raise DeploymentError(
            "osa-dev CloudFormation update wait failed (exit 1); credential-marker"
        )

    monkeypatch.setattr(DEPLOYMENT, "deploy_dev", fail_deployment)

    assert DEPLOYMENT.main([]) == 1
    assert "credential-marker" in capsys.readouterr().err
    content = summary.read_text(encoding="utf-8")
    assert "CloudFormation deployment: FAIL" in content
    assert "Failure stage: CloudFormation update wait" in content
    assert "CloudFormation rollback: NOT VERIFIED" in content
    assert "credential-marker" not in content
    assert "123456789012" not in content
    assert "dev.example.com" not in content


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


def test_validate_only_checks_collector_endpoint_and_token_type_before_success(
    monkeypatch, capsys
) -> None:
    runner, calls = runner_for()
    monkeypatch.setattr(DEPLOYMENT.subprocess, "run", runner)
    for key, value in {
        "AWS_REGION": REGION,
        "DEV_DEPLOY_ROLE_ARN": ROLE_ARN,
        "DEV_EXECUTION_ROLE_ARN": EXECUTION_ROLE_ARN,
        "ECR_REPOSITORY_URI": REPOSITORY_URI,
        "IMAGE_REF": IMAGE_REF,
        "RELEASE_VERSION": VERSION,
        "OSA_AMI_ID": "ami-0123456789abcdef0",
        "OSA_INSTANCE_TYPE": "t3.small",
        "OSA_DEV_HOSTNAME": "dev.example.com",
    }.items():
        monkeypatch.setenv(key, value)

    assert main(["--validate-only"]) == 0
    output = capsys.readouterr().out
    assert "preflight is valid" in output
    assert len(calls) == 2
    assert all("--with-decryption" not in call for call in calls)


def test_validate_only_fails_when_otlp_token_is_not_securestring(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        calls.append(args)
        stdout = (
            "http://10.40.1.25:4318"
            if args[:3] == ["aws", "cloudformation", "describe-stacks"]
            else "String"
        )
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(DEPLOYMENT.subprocess, "run", runner)
    for key, value in {
        "AWS_REGION": REGION,
        "DEV_DEPLOY_ROLE_ARN": ROLE_ARN,
        "DEV_EXECUTION_ROLE_ARN": EXECUTION_ROLE_ARN,
        "ECR_REPOSITORY_URI": REPOSITORY_URI,
        "IMAGE_REF": IMAGE_REF,
        "RELEASE_VERSION": VERSION,
        "OSA_AMI_ID": "ami-0123456789abcdef0",
        "OSA_INSTANCE_TYPE": "t3.small",
        "OSA_DEV_HOSTNAME": "dev.example.com",
    }.items():
        monkeypatch.setenv(key, value)

    assert main(["--validate-only"]) == 1
    assert "must exist as a SecureString" in capsys.readouterr().err
    assert len(calls) == 2


def test_failed_stack_update_does_not_wait_or_proceed(tmp_path: Path) -> None:
    runner, calls = runner_for(fail_command="aws cloudformation update-stack")

    with pytest.raises(DeploymentError, match="osa-dev CloudFormation update failed") as error:
        deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 3
    assert "credential-marker" not in str(error.value)


def test_failed_stack_wait_reports_failure_and_stops(tmp_path: Path) -> None:
    runner, calls = runner_for(fail_command="aws cloudformation wait stack-update-complete")

    with pytest.raises(DeploymentError, match="osa-dev CloudFormation update wait failed"):
        deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 4


def test_missing_otlp_securestring_fails_before_cloudformation_update() -> None:
    runner, calls = runner_for(fail_command="aws ssm get-parameter")

    with pytest.raises(DeploymentError, match="OTLP authentication parameter") as error:
        deploy_dev(valid_inputs(), runner=runner)

    assert "credential-marker" not in str(error.value)
    assert len(calls) == 2
    assert not any(command[:3] == ["aws", "cloudformation", "update-stack"] for command in calls)


def test_non_securestring_otlp_parameter_fails_before_cloudformation_update() -> None:
    calls: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        calls.append(args)
        stdout = (
            "http://10.40.1.25:4318"
            if args[:3] == ["aws", "cloudformation", "describe-stacks"]
            else "String"
        )
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    with pytest.raises(DeploymentError, match="must exist as a SecureString"):
        deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 2
    assert not any(command[:3] == ["aws", "cloudformation", "update-stack"] for command in calls)


@pytest.mark.parametrize("endpoint", ["None", "http://8.8.8.8:4318", "http://10.40.1.25:4317"])
def test_missing_or_nonprivate_collector_endpoint_fails_before_update(endpoint: str) -> None:
    calls: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=endpoint, stderr="")

    with pytest.raises(DeploymentError, match="private Collector endpoint"):
        deploy_dev(valid_inputs(), runner=runner)

    assert len(calls) == 1
    assert not any(command[:3] == ["aws", "cloudformation", "update-stack"] for command in calls)


def test_dev_manifest_cannot_be_replaced_with_production_configuration(tmp_path: Path) -> None:
    bad_manifest = tmp_path / "osa-dev.json"
    data = json.loads(Path("deploy/cloudformation/environments/osa-dev.json").read_text())
    data["StackName"] = "osa-prod"
    bad_manifest.write_text(json.dumps(data), encoding="utf-8")
    runner, calls = runner_for()

    with pytest.raises(DeploymentError, match="Development manifest"):
        deploy_dev(valid_inputs(), runner=runner, manifest_path=bad_manifest)

    assert calls == []
