#!/usr/bin/env python3
"""Validate release inputs and update only the osa-dev CloudFormation stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "deploy/cloudformation/environments/osa-dev.json"
EXPECTED_TEMPLATE = ROOT / "deploy/cloudformation/osa-application.yaml"
EXPECTED_RUNTIME_INPUTS = [
    "ImageDigest",
    "ReleaseVersion",
    "AmiId",
    "InstanceType",
    "PublicHostname",
]
REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-gov|-iso|-isob)?-[a-z]+-\d$")
ROLE_ARN_PATTERN = re.compile(
    r"^arn:(aws|aws-us-gov|aws-cn):iam::(?P<account>\d{12}):role/osa-foundation/"
    r"(?P<name>osa-foundation-osa-dev-deploy|osa-foundation-osa-dev-application-execution)$"
)
REPOSITORY_PATTERN = re.compile(
    r"^(?P<account>\d{12})\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com(?:\.cn)?/"
    r"open-sales-analytics$"
)
IMAGE_REF_PATTERN = re.compile(
    r"^(?P<repository>\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/"
    r"open-sales-analytics)@sha256:(?P<digest>[a-f0-9]{64})$"
)
VERSION_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$")
AMI_PATTERN = re.compile(r"^ami-[a-f0-9]{8,17}$")
INSTANCE_TYPE_PATTERN = re.compile(r"^[a-z][0-9][a-z0-9]*\.[a-z0-9]+$")
HOSTNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class DeploymentError(RuntimeError):
    """An invalid deployment or failed AWS command with credentials omitted."""


@dataclass(frozen=True)
class DeploymentInputs:
    region: str
    deploy_role_arn: str
    execution_role_arn: str
    repository_uri: str
    image_ref: str
    release_version: str
    ami_id: str
    instance_type: str
    hostname: str


def validate_manifest(manifest_path: Path = MANIFEST_PATH) -> Path:
    """Require the checked-in dev manifest to target only the shared app template."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(
            f"Development manifest is unavailable or invalid ({type(exc).__name__})."
        ) from None
    if not isinstance(manifest, dict):
        raise DeploymentError("Development manifest must be a JSON object.")
    expected = {
        "StackName": "osa-dev",
        "TemplateFile": "../osa-application.yaml",
        "Parameters": {"Environment": "development"},
        "RuntimeInputs": EXPECTED_RUNTIME_INPUTS,
        "FoundationRoleOutputs": {
            "CloudFormationExecutionRole": "DevApplicationExecutionRoleArn",
            "GitHubDeployRole": "DevDeployRoleArn",
        },
    }
    if manifest != expected:
        raise DeploymentError("Development manifest does not match the osa-dev release contract.")
    template = (manifest_path.parent / manifest["TemplateFile"]).resolve()
    if template != EXPECTED_TEMPLATE.resolve() or not template.is_file():
        raise DeploymentError(
            "Development manifest must resolve to the shared application template."
        )
    return template


def validate_inputs(inputs: DeploymentInputs, *, stack_name: str = "osa-dev") -> str:
    """Validate every runtime input before any AWS command can run."""
    if stack_name != "osa-dev":
        raise DeploymentError("Development deployment is restricted to stack osa-dev.")
    if not REGION_PATTERN.fullmatch(inputs.region):
        raise DeploymentError("AWS region is missing or malformed.")
    role_match = ROLE_ARN_PATTERN.fullmatch(inputs.deploy_role_arn)
    execution_match = ROLE_ARN_PATTERN.fullmatch(inputs.execution_role_arn)
    if role_match is None or role_match.group("name") != "osa-foundation-osa-dev-deploy":
        raise DeploymentError("Development deployment role ARN is missing or out of scope.")
    if (
        execution_match is None
        or execution_match.group("name") != "osa-foundation-osa-dev-application-execution"
    ):
        raise DeploymentError(
            "Development CloudFormation execution role ARN is missing or out of scope."
        )
    if role_match.group("account") != execution_match.group("account"):
        raise DeploymentError("Development role ARNs must belong to the same AWS account.")

    repository_match = REPOSITORY_PATTERN.fullmatch(inputs.repository_uri)
    image_match = IMAGE_REF_PATTERN.fullmatch(inputs.image_ref)
    if repository_match is None or image_match is None:
        raise DeploymentError(
            "Published ECR repository URI or digest-pinned image reference is missing or malformed."
        )
    if image_match.group("repository") != inputs.repository_uri:
        raise DeploymentError(
            "Published image reference does not match the configured ECR repository."
        )
    if repository_match.group("region") != inputs.region or repository_match.group(
        "account"
    ) != role_match.group("account"):
        raise DeploymentError(
            "ECR repository and development roles must match the configured AWS region and account."
        )
    if not VERSION_PATTERN.fullmatch(inputs.release_version):
        raise DeploymentError("Published release version is missing or malformed.")
    if not AMI_PATTERN.fullmatch(inputs.ami_id):
        raise DeploymentError("Development AMI ID is missing or malformed.")
    if not INSTANCE_TYPE_PATTERN.fullmatch(inputs.instance_type):
        raise DeploymentError("Development EC2 instance type is missing or malformed.")
    if not HOSTNAME_PATTERN.fullmatch(inputs.hostname):
        raise DeploymentError("Development hostname is missing or malformed.")
    if len(inputs.hostname) > 253:
        raise DeploymentError("Development hostname is longer than 253 characters.")
    return image_match.group("digest")


def update_stack_command(inputs: DeploymentInputs, digest: str, template_path: Path) -> list[str]:
    return [
        "aws",
        "cloudformation",
        "update-stack",
        "--stack-name",
        "osa-dev",
        "--template-body",
        f"file://{template_path}",
        "--capabilities",
        "CAPABILITY_NAMED_IAM",
        "--role-arn",
        inputs.execution_role_arn,
        "--parameters",
        "ParameterKey=Environment,ParameterValue=development",
        f"ParameterKey=ImageDigest,ParameterValue={digest}",
        f"ParameterKey=ReleaseVersion,ParameterValue={inputs.release_version}",
        f"ParameterKey=AmiId,ParameterValue={inputs.ami_id}",
        f"ParameterKey=InstanceType,ParameterValue={inputs.instance_type}",
        f"ParameterKey=PublicHostname,ParameterValue={inputs.hostname}",
        "--region",
        inputs.region,
    ]


def _run(runner: CommandRunner, command: Sequence[str], *, step: str) -> None:
    try:
        result = runner(list(command), capture_output=True, text=True, check=False)
    except OSError as exc:
        raise DeploymentError(f"{step} could not start ({type(exc).__name__}).") from None
    if result.returncode != 0:
        raise DeploymentError(f"{step} failed (exit {result.returncode}); deployment stopped.")


def deploy_dev(
    inputs: DeploymentInputs,
    *,
    runner: CommandRunner = subprocess.run,
    manifest_path: Path = MANIFEST_PATH,
    stack_name: str = "osa-dev",
) -> None:
    digest = validate_inputs(inputs, stack_name=stack_name)
    template_path = validate_manifest(manifest_path)
    _run(
        runner,
        update_stack_command(inputs, digest, template_path),
        step="osa-dev CloudFormation update",
    )
    _run(
        runner,
        [
            "aws",
            "cloudformation",
            "wait",
            "stack-update-complete",
            "--stack-name",
            "osa-dev",
            "--region",
            inputs.region,
        ],
        step="osa-dev CloudFormation update wait",
    )


def write_summary(
    path: Path,
    inputs: DeploymentInputs,
    *,
    result: str,
    failure_stage: str | None,
) -> None:
    """Write only allowlisted dev release metadata and sanitized deployment outcomes."""
    image = IMAGE_REF_PATTERN.fullmatch(inputs.image_ref)
    digest = image.group("digest") if image is not None else None
    version = inputs.release_version if VERSION_PATTERN.fullmatch(inputs.release_version) else None
    deployment = "PASS" if result == "PASS" else "FAIL"
    readiness = "PENDING" if deployment == "PASS" else "NOT RUN"
    smoke = "PENDING" if deployment == "PASS" else "NOT RUN"
    lines = [
        "## Development deployment evidence",
        "",
        "- Environment: development",
    ]
    if version is not None:
        lines.extend((f"- Image tag: `{version}`", f"- Release version: `{version}`"))
    if digest is not None:
        lines.append(f"- Image digest: `sha256:{digest}`")
    lines.extend(
        (
            f"- CloudFormation deployment: {deployment}",
            f"- Readiness: {readiness}",
            f"- Sample analytics smoke: {smoke}",
            "- Temporary sample cleanup: NOT RUN (verification has not started)",
            "- CloudFormation rollback: NOT VERIFIED"
            if deployment == "FAIL"
            else "- CloudFormation rollback: NOT REQUIRED",
        )
    )
    if failure_stage is not None:
        lines.append(f"- Failure stage: {failure_stage}")
    lines.extend((f"- Result: {deployment}", ""))
    try:
        with path.open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines))
    except OSError as exc:
        raise DeploymentError(
            f"Unable to write deployment summary ({type(exc).__name__})."
        ) from None


def inputs_from_environment(environment: dict[str, str] | None = None) -> DeploymentInputs:
    env = os.environ if environment is None else environment
    return DeploymentInputs(
        region=env.get("AWS_REGION", ""),
        deploy_role_arn=env.get("DEV_DEPLOY_ROLE_ARN", ""),
        execution_role_arn=env.get("DEV_EXECUTION_ROLE_ARN", ""),
        repository_uri=env.get("ECR_REPOSITORY_URI", ""),
        image_ref=env.get("IMAGE_REF", ""),
        release_version=env.get("RELEASE_VERSION", ""),
        ami_id=env.get("OSA_AMI_ID", ""),
        instance_type=env.get("OSA_INSTANCE_TYPE", ""),
        hostname=env.get("OSA_DEV_HOSTNAME", ""),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only", action="store_true", help="validate configuration without calling AWS"
    )
    args = parser.parse_args(argv)
    env = dict(os.environ)
    inputs = inputs_from_environment(env)
    summary_value = env.get("GITHUB_STEP_SUMMARY")
    summary_path = Path(summary_value) if summary_value else None
    try:
        validate_inputs(inputs)
        validate_manifest()
        if args.validate_only:
            print("osa-dev deployment configuration is valid.")
            return 0
        deploy_dev(inputs)
        if summary_path is not None:
            write_summary(summary_path, inputs, result="PASS", failure_stage=None)
    except DeploymentError as exc:
        if summary_path is not None and not args.validate_only:
            message = str(exc).lower()
            if "update wait" in message:
                failure_stage = "CloudFormation update wait"
            elif "cloudformation update" in message:
                failure_stage = "CloudFormation update"
            else:
                failure_stage = "Deployment configuration validation"
            try:
                write_summary(
                    summary_path,
                    inputs,
                    result="FAIL",
                    failure_stage=failure_stage,
                )
            except DeploymentError:
                pass
        print(f"osa-dev deployment failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
