#!/usr/bin/env python3
"""Select the current dev digest and promote it without rebuilding."""

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

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy/cloudformation/osa-application.yaml"
REPO_RE = re.compile(
    r"^(?P<account>\d{12})\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com(?:\.cn)?/open-sales-analytics$"
)
DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
VERSION_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$")
ROLE_RE = re.compile(
    r"^arn:(?:aws|aws-us-gov|aws-cn):iam::(?P<account>\d{12}):role/osa-foundation/(?P<role>osa-foundation-osa-production-source-read|osa-foundation-osa-prod-promotion|osa-foundation-osa-prod-application-execution)$"
)


class PromotionError(RuntimeError):
    """Safe promotion failure without AWS response data."""


@dataclass(frozen=True)
class Config:
    region: str
    repository: str
    source_read_role: str
    promotion_role: str
    execution_role: str
    ami: str
    instance_type: str
    hostname: str


@dataclass(frozen=True)
class Release:
    digest: str
    version: str


def validate_config(config: Config) -> None:
    repo = REPO_RE.fullmatch(config.repository)
    source_role = ROLE_RE.fullmatch(config.source_read_role)
    promote = ROLE_RE.fullmatch(config.promotion_role)
    execution = ROLE_RE.fullmatch(config.execution_role)
    if not re.fullmatch(r"[a-z]{2}(?:-gov|-iso|-isob)?-[a-z]+-\d", config.region):
        raise PromotionError("AWS region is missing or malformed.")
    if (
        repo is None
        or source_role is None
        or source_role.group("role") != "osa-foundation-osa-production-source-read"
    ):
        raise PromotionError(
            "ECR repository or development source-read role is missing or out of scope."
        )
    if promote is None or promote.group("role") != "osa-foundation-osa-prod-promotion":
        raise PromotionError("Production promotion role is missing or out of scope.")
    if (
        execution is None
        or execution.group("role") != "osa-foundation-osa-prod-application-execution"
    ):
        raise PromotionError("Production execution role is missing or out of scope.")
    if (
        repo.group("region") != config.region
        or repo.group("account") != promote.group("account")
        or promote.group("account") != execution.group("account")
        or source_role.group("account") != promote.group("account")
    ):
        raise PromotionError(
            "ECR repository and production roles must match the configured account and region."
        )


def parse_release(stdout: str, stack: str, repository: str) -> Release:
    try:
        data = json.loads(stdout)
        stacks = data["Stacks"]
        if (
            len(stacks) != 1
            or stacks[0].get("StackName") != stack
            or stacks[0].get("StackStatus")
            not in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"}
        ):
            raise ValueError
        outputs = {item["OutputKey"]: item["OutputValue"] for item in stacks[0]["Outputs"]}
        image_ref, version = outputs["ImageReference"], outputs["ReleaseVersion"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise PromotionError(f"{stack} release metadata is missing or malformed.") from None
    match = re.fullmatch(r"(.+)@sha256:([a-f0-9]{64})", image_ref)
    if match is None or match.group(1) != repository:
        raise PromotionError(
            f"{stack} release uses an invalid digest or unexpected ECR repository."
        )
    if not VERSION_RE.fullmatch(version):
        raise PromotionError(f"{stack} release version is missing or malformed.")
    return Release(match.group(2), version)


def run(
    runner: Callable[..., subprocess.CompletedProcess[str]], command: list[str], label: str
) -> str:
    try:
        result = runner(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise PromotionError(f"{label} could not start ({type(exc).__name__}).") from None
    if result.returncode:
        raise PromotionError(f"{label} failed (exit {result.returncode}).")
    return result.stdout


def describe(
    runner: Callable[..., subprocess.CompletedProcess[str]], stack: str, config: Config
) -> Release:
    out = run(
        runner,
        [
            "aws",
            "cloudformation",
            "describe-stacks",
            "--stack-name",
            stack,
            "--region",
            config.region,
            "--output",
            "json",
        ],
        f"Read {stack}",
    )
    return parse_release(out, stack, config.repository)


def update_command(config: Config, release: Release) -> list[str]:
    return [
        "aws",
        "cloudformation",
        "update-stack",
        "--stack-name",
        "osa-prod",
        "--template-body",
        f"file://{TEMPLATE}",
        "--capabilities",
        "CAPABILITY_NAMED_IAM",
        "--role-arn",
        config.execution_role,
        "--parameters",
        "ParameterKey=Environment,ParameterValue=production",
        f"ParameterKey=ImageDigest,ParameterValue={release.digest}",
        f"ParameterKey=ReleaseVersion,ParameterValue={release.version}",
        f"ParameterKey=AmiId,ParameterValue={config.ami}",
        f"ParameterKey=InstanceType,ParameterValue={config.instance_type}",
        f"ParameterKey=PublicHostname,ParameterValue={config.hostname}",
        "--region",
        config.region,
    ]


def write_summary(source: Release, previous: Release, env: dict[str, str]) -> None:
    path = env.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(
                "## Production promotion\n\n| Release | Digest | Version |\n|---|---|---|\n"
            )
            stream.write(f"| Dev source | {source.digest} | {source.version} |\n")
            stream.write(f"| Production target | {source.digest} | {source.version} |\n")
            stream.write(f"| Previous production | {previous.digest} | {previous.version} |\n")


def promote(
    config: Config,
    source: Release,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    env: dict[str, str],
) -> Release:
    validate_config(config)
    if not DIGEST_RE.fullmatch(source.digest) or not VERSION_RE.fullmatch(source.version):
        raise PromotionError("Development release metadata failed validation.")
    previous = describe(runner, "osa-prod", config)
    write_summary(source, previous, env)
    run(runner, update_command(config, source), "osa-prod update")
    run(
        runner,
        [
            "aws",
            "cloudformation",
            "wait",
            "stack-update-complete",
            "--stack-name",
            "osa-prod",
            "--region",
            config.region,
        ],
        "osa-prod update wait",
    )
    return previous


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--read-dev", action="store_true")
    group.add_argument("--promote", action="store_true")
    group.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    config = Config(
        env.get("AWS_REGION", ""),
        env.get("ECR_REPOSITORY_URI", ""),
        env.get("PROD_SOURCE_READ_ROLE_ARN", ""),
        env.get("PROD_PROMOTION_ROLE_ARN", ""),
        env.get("PROD_EXECUTION_ROLE_ARN", ""),
        env.get("OSA_AMI_ID", ""),
        env.get("OSA_INSTANCE_TYPE", ""),
        env.get("OSA_PROD_HOSTNAME", ""),
    )
    try:
        validate_config(config)
        if args.validate_only:
            print("Production promotion configuration is valid.")
            return 0
        if args.read_dev:
            release = describe(subprocess.run, "osa-dev", config)
            output = env.get("GITHUB_OUTPUT")
            if output:
                with Path(output).open("a", encoding="utf-8") as stream:
                    stream.write(
                        f"image_digest={release.digest}\nrelease_version={release.version}\n"
                    )
            print("osa-dev release metadata validated.")
        else:
            source = Release(env.get("DEV_IMAGE_DIGEST", ""), env.get("DEV_RELEASE_VERSION", ""))
            promote(config, source, subprocess.run, env)
            print("osa-prod update completed.")
    except PromotionError as exc:
        print(f"Production promotion failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
