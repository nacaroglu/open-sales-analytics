#!/usr/bin/env python3
"""Select the current dev digest and promote it without rebuilding."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from otlp_preflight import OtlpPreflightError, validate_otlp_prerequisites

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy/cloudformation/osa-application.yaml"
REPO_RE = re.compile(
    r"^(?P<account>\d{12})\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com(?:\.cn)?/open-sales-analytics$"
)
DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
VERSION_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$")
HOST_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I
)
DATASET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")
EXPECTED_SAMPLE = {"gross_sales": "675816.7000", "orders": 10000, "units_sold": 24380}
EXPECTED_SAMPLE_ROWS = 14397
EXPECTED_SAMPLE_DATES = {"min": "2024-01-01", "max": "2025-12-31"}
VERIFY_TIMEOUT_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 10
STACK_SETTLEMENT_TIMEOUT_SECONDS = 600
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
            not in {
                "CREATE_COMPLETE",
                "UPDATE_COMPLETE",
                "IMPORT_COMPLETE",
                "UPDATE_ROLLBACK_COMPLETE",
            }
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


def wait_for_stack_settlement(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    config: Config,
    *,
    timeout_seconds: float = STACK_SETTLEMENT_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait until a failed CloudFormation update finishes its automatic rollback."""
    complete = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}
    failed = {"UPDATE_ROLLBACK_FAILED", "ROLLBACK_FAILED", "CREATE_FAILED"}
    in_progress = {
        "UPDATE_FAILED",
        "CREATE_IN_PROGRESS",
        "UPDATE_IN_PROGRESS",
        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
        "UPDATE_ROLLBACK_IN_PROGRESS",
        "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
        "ROLLBACK_IN_PROGRESS",
        "IMPORT_IN_PROGRESS",
    }
    deadline = monotonic() + timeout_seconds
    while True:
        raw = run(
            runner,
            [
                "aws",
                "cloudformation",
                "describe-stacks",
                "--stack-name",
                "osa-prod",
                "--region",
                config.region,
                "--output",
                "json",
            ],
            "osa-prod rollback settlement lookup",
        )
        try:
            payload = json.loads(raw)
            stacks = payload["Stacks"]
            status = stacks[0]["StackStatus"] if len(stacks) == 1 else ""
        except (KeyError, TypeError, json.JSONDecodeError):
            raise PromotionError(
                "osa-prod stack status is missing or malformed during rollback."
            ) from None
        if status in complete:
            return
        if status in failed:
            raise PromotionError(
                "CloudFormation could not complete its automatic production rollback."
            )
        remaining = deadline - monotonic()
        if status not in in_progress:
            raise PromotionError("osa-prod entered an unexpected status during rollback.")
        if remaining <= 0:
            raise PromotionError("Timed out waiting for the production stack update to settle.")
        sleep(min(5.0, remaining))


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


def write_summary(
    source: Release,
    previous: Release | None,
    env: dict[str, str],
    *,
    verification: str,
    rollback: str,
    readiness: str = "NOT RUN",
    smoke: str = "NOT RUN",
    cleanup: str = "NOT RUN",
    failure_stage: str | None = None,
    rollback_failure_stage: str | None = None,
) -> None:
    path = env.get("GITHUB_STEP_SUMMARY")
    if path:
        previous_version = previous.version if previous is not None else "unavailable"
        previous_digest = f"sha256:{previous.digest}" if previous is not None else "unavailable"
        try:
            with Path(path).open("a", encoding="utf-8") as stream:
                stream.write(
                    "## Production promotion evidence\n\n"
                    "- Environment: production\n"
                    f"- Image tag: `{source.version}`\n"
                    f"- Release version: `{source.version}`\n"
                    f"- Image digest: `sha256:{source.digest}`\n"
                    f"- Previous production image tag: `{previous_version}`\n"
                    f"- Previous production version: `{previous_version}`\n"
                    f"- Previous production digest: `{previous_digest}`\n"
                )
                stream.write(f"- Readiness: {readiness}\n")
                stream.write(f"- Sample analytics smoke: {smoke}\n")
                stream.write(f"- Temporary sample cleanup: {cleanup}\n")
                stream.write(f"\n- Production verification: {verification}\n")
                stream.write(f"- Rollback: {rollback}\n")
                if failure_stage is not None:
                    stream.write(f"- Failure stage: {failure_stage}\n")
                if rollback_failure_stage is not None:
                    stream.write(f"- Rollback failure stage: {rollback_failure_stage}\n")
                stream.write(f"- Result: {'PASS' if verification == 'PASS' else 'FAIL'}\n")
        except OSError as exc:
            raise PromotionError(
                f"Unable to write promotion summary ({type(exc).__name__})."
            ) from None


def verification_summary_state(error: PromotionError) -> tuple[str, str, str]:
    """Map safe failure categories to summary fields without recording error text."""
    message = str(error).lower()
    if "readiness" in message:
        return "Production readiness", "FAIL", "NOT RUN"
    if "sample" in message or "analytics" in message:
        return "Sample analytics smoke", "PASS", "FAIL"
    return "Production verification", "NOT RUN", "NOT RUN"


def _http_request(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout: float,
    *,
    opener: Callable[..., Any],
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener(request, timeout=timeout, context=ssl.create_default_context()) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise PromotionError(f"Production HTTPS request failed ({type(exc).__name__}).") from None


def _json_body(status: int, body: bytes, expected_status: int, label: str) -> dict:
    if status != expected_status:
        raise PromotionError(f"{label} returned HTTP {status}; expected {expected_status}.")
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise PromotionError(f"{label} returned malformed JSON.") from None
    if not isinstance(value, dict):
        raise PromotionError(f"{label} returned malformed JSON.")
    return value


def verify_production(
    config: Config,
    release: Release,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout_seconds: float = VERIFY_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait for the public production health contract and verify its sample analytics path."""
    if not HOST_RE.fullmatch(config.hostname):
        raise PromotionError("Production hostname is missing or malformed.")
    base_url = f"https://{config.hostname}"
    deadline = monotonic() + timeout_seconds
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PromotionError("Production readiness timed out.")
        try:
            status, body = _http_request(
                f"{base_url}/health/ready",
                "GET",
                {},
                None,
                min(HTTP_TIMEOUT_SECONDS, remaining),
                opener=opener,
            )
            readiness = _json_body(status, body, 200, "Production readiness endpoint")
            if (
                readiness.get("status") == "ready"
                and readiness.get("environment") == "production"
                and readiness.get("version") == release.version
            ):
                break
            # The previous instance may still answer while CloudFormation replaces it.
        except PromotionError:
            pass
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PromotionError("Production readiness timed out.")
        sleep(min(2.0, remaining))

    status, body = _http_request(
        f"{base_url}/api/datasets/sample",
        "POST",
        {},
        b"",
        HTTP_TIMEOUT_SECONDS,
        opener=opener,
    )
    created = _json_body(status, body, 201, "Production sample creation")
    dataset_id = created.get("dataset_id")
    token = created.get("token")
    if not isinstance(dataset_id, str) or not DATASET_ID_RE.fullmatch(dataset_id):
        raise PromotionError("Production sample response omitted a valid dataset ID.")
    if not isinstance(token, str) or not token:
        raise PromotionError("Production sample response omitted its access token.")
    print(f"::add-mask::{token}", flush=True)
    print(f"::add-mask::Bearer {token}", flush=True)

    operation_error: PromotionError | None = None
    try:
        metadata = created.get("meta")
        if (
            not isinstance(metadata, dict)
            or metadata.get("currency") != "USD"
            or metadata.get("date_range") != EXPECTED_SAMPLE_DATES
            or metadata.get("row_count") != EXPECTED_SAMPLE_ROWS
            or created.get("warnings") != []
        ):
            raise PromotionError("Production sample metadata does not match the bundled sample.")
        status, analytics_body = _http_request(
            f"{base_url}/api/datasets/{dataset_id}/analytics",
            "GET",
            {"Authorization": f"Bearer {token}"},
            None,
            HTTP_TIMEOUT_SECONDS,
            opener=opener,
        )
        analytics = _json_body(status, analytics_body, 200, "Production sample analytics")
        kpis = analytics.get("kpis")
        if (
            not isinstance(kpis, dict)
            or any(kpis.get(key) != value for key, value in EXPECTED_SAMPLE.items())
            or not isinstance(analytics.get("trend"), list)
            or not analytics["trend"]
            or not isinstance(analytics.get("top_products"), list)
            or not analytics["top_products"]
        ):
            raise PromotionError("Production sample analytics do not match the bundled sample.")
    except PromotionError as exc:
        operation_error = exc

    try:
        status, _ = _http_request(
            f"{base_url}/api/datasets/{dataset_id}",
            "DELETE",
            {"Authorization": f"Bearer {token}"},
            None,
            HTTP_TIMEOUT_SECONDS,
            opener=opener,
        )
        if status != 204:
            raise PromotionError(f"Production temporary sample cleanup returned HTTP {status}.")
    except PromotionError as cleanup_error:
        if operation_error is not None:
            raise PromotionError(
                f"{operation_error}; production temporary sample cleanup also failed."
            ) from None
        raise cleanup_error
    if operation_error is not None:
        raise operation_error


def promote(
    config: Config,
    source: Release,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    env: dict[str, str],
    verifier: Callable[[Config, Release], None] = verify_production,
) -> Release:
    validate_config(config)
    if not DIGEST_RE.fullmatch(source.digest) or not VERSION_RE.fullmatch(source.version):
        raise PromotionError("Development release metadata failed validation.")
    try:
        validate_otlp_prerequisites(config.region, "production", runner=runner)
    except OtlpPreflightError as exc:
        raise PromotionError(f"Production OTLP prerequisites failed: {exc}") from None
    try:
        previous = describe(runner, "osa-prod", config)
    except PromotionError:
        write_summary(
            source,
            None,
            env,
            verification="FAIL",
            rollback="NOT RUN",
            failure_stage="Prior production metadata lookup",
        )
        raise
    try:
        run(runner, update_command(config, source), "osa-prod update")
        try:
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
        except PromotionError:
            wait_for_stack_settlement(runner, config)
            raise
        if describe(runner, "osa-prod", config) != source:
            raise PromotionError("osa-prod release metadata does not match the promoted release.")
        verifier(config, source)
        write_summary(
            source,
            previous,
            env,
            verification="PASS",
            rollback="not required",
            readiness="PASS",
            smoke="PASS",
            cleanup="PASS",
        )
    except PromotionError as promotion_error:
        failure_stage, readiness, sample_analytics = verification_summary_state(promotion_error)
        try:
            current = describe(runner, "osa-prod", config)
            if current != previous:
                run(runner, update_command(config, previous), "osa-prod rollback update")
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
                    "osa-prod rollback wait",
                )
            if describe(runner, "osa-prod", config) != previous:
                raise PromotionError(
                    "Restored production digest or version does not match the previous release."
                )
            verifier(config, previous)
            if describe(runner, "osa-prod", config) != previous:
                raise PromotionError("Production release changed during rollback verification.")
            write_summary(
                source,
                previous,
                env,
                verification="FAIL",
                rollback="PASS",
                failure_stage=failure_stage,
                readiness=readiness,
                smoke=sample_analytics,
            )
        except PromotionError as rollback_error:
            rollback_stage = "Production rollback verification"
            rollback_message = str(rollback_error).lower()
            if "rollback update" in rollback_message:
                rollback_stage = "Production rollback update"
            elif "rollback wait" in rollback_message:
                rollback_stage = "Production rollback readiness wait"
            try:
                write_summary(
                    source,
                    previous,
                    env,
                    verification="FAIL",
                    rollback="FAILED",
                    failure_stage=failure_stage,
                    readiness=readiness,
                    smoke=sample_analytics,
                    rollback_failure_stage=rollback_stage,
                )
            except PromotionError:
                pass
            raise PromotionError(
                f"{promotion_error}; production rollback failed: {rollback_error}"
            ) from None
        raise PromotionError(
            f"{promotion_error}; previous production release was restored and verified."
        ) from None
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
