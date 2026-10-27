#!/usr/bin/env python3
"""Verify the dev release through HTTPS and record non-secret results."""

from __future__ import annotations

import argparse
import base64
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

AWS_RUNNER = Callable[..., subprocess.CompletedProcess[str]]
HTTP_OPENER = Callable[..., object]
REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-gov|-iso|-isob)?-[a-z]+-\d$")
HOST_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I)
IMAGE_DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
DIGEST_PATTERN = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$")
VERSION_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{7}$")
DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")
SMOKE_PARAMETER = "/osa/dev/caddy/smoke-credential"
EXPECTED_SAMPLE = {"gross_sales": "675816.7000", "orders": 10000, "units_sold": 24380}
EXPECTED_SAMPLE_ROWS = 14397
EXPECTED_SAMPLE_DATES = {"min": "2024-01-01", "max": "2025-12-31"}
DEFAULT_TIMEOUT_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 10


class VerificationError(RuntimeError):
    """A failed verification with no response body, token, or secret attached."""


@dataclass(frozen=True)
class VerificationInputs:
    region: str
    hostname: str
    expected_digest: str
    expected_version: str


def validate_inputs(inputs: VerificationInputs) -> None:
    if not REGION_PATTERN.fullmatch(inputs.region):
        raise VerificationError("AWS region is missing or malformed.")
    if not HOST_PATTERN.fullmatch(inputs.hostname):
        raise VerificationError("Development hostname is missing or malformed.")
    if not DIGEST_PATTERN.fullmatch(inputs.expected_digest):
        raise VerificationError("Published image digest is missing or malformed.")
    if not VERSION_PATTERN.fullmatch(inputs.expected_version):
        raise VerificationError("Published release version is missing or malformed.")


def _run_aws(
    runner: AWS_RUNNER,
    command: Sequence[str],
    *,
    step: str,
) -> str:
    try:
        result = runner(list(command), capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VerificationError(f"{step} could not start ({type(exc).__name__}).") from None
    if result.returncode != 0:
        raise VerificationError(f"{step} failed (exit {result.returncode}).")
    return result.stdout.strip()


def _mask_github_value(value: str) -> None:
    print(f"::add-mask::{value}", flush=True)


def read_smoke_credential(region: str, *, runner: AWS_RUNNER = subprocess.run) -> tuple[str, str]:
    """Read and immediately mask a dedicated user:password SSM SecureString."""
    value = _run_aws(
        runner,
        [
            "aws", "ssm", "get-parameter", "--name", SMOKE_PARAMETER,
            "--with-decryption", "--query", "Parameter.Value", "--output", "text",
            "--region", region,
        ],
        step="Development smoke credential retrieval",
    )
    if not value or "\n" in value or "\r" in value:
        raise VerificationError("Development smoke credential is missing or malformed.")
    username, separator, password = value.partition(":")
    if not separator or not username or not password:
        raise VerificationError("Development smoke credential is missing or malformed.")
    # GitHub masks every exact value before it can appear in later command output.
    _mask_github_value(value)
    _mask_github_value(password)
    _mask_github_value(_basic_header(username, password))
    return username, password


def read_deployed_release(
    region: str,
    *,
    runner: AWS_RUNNER = subprocess.run,
) -> tuple[str, str]:
    raw = _run_aws(
        runner,
        [
            "aws", "cloudformation", "describe-stacks", "--stack-name", "osa-dev",
            "--region", region, "--output", "json",
        ],
        step="osa-dev release metadata lookup",
    )
    try:
        payload = json.loads(raw)
        outputs = payload["Stacks"][0]["Outputs"]
        values = {item["OutputKey"]: item["OutputValue"] for item in outputs}
        digest = values["ImageDigest"]
        version = values["ReleaseVersion"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise VerificationError("osa-dev stack release metadata is missing or malformed.") from None
    if not IMAGE_DIGEST_PATTERN.fullmatch(digest) or not VERSION_PATTERN.fullmatch(version):
        raise VerificationError("osa-dev stack release metadata is missing or malformed.")
    return digest, version


def _http_request(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout: float,
    *,
    opener: HTTP_OPENER = urllib.request.urlopen,
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        # The default SSL context verifies the hostname and certificate chain.
        with opener(request, timeout=timeout, context=ssl.create_default_context()) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise VerificationError(f"HTTPS request failed ({type(exc).__name__}).") from None


def _basic_header(username: str, password: str) -> str:
    encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _json_body(status: int, body: bytes, expected_status: int, step: str) -> dict:
    if status != expected_status:
        raise VerificationError(f"{step} returned HTTP {status}; expected {expected_status}.")
    try:
        result = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise VerificationError(f"{step} returned malformed JSON.") from None
    if not isinstance(result, dict):
        raise VerificationError(f"{step} returned malformed JSON.")
    return result


def wait_until_ready(
    base_url: str,
    username: str,
    password: str,
    expected_version: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    opener: HTTP_OPENER = urllib.request.urlopen,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    deadline = monotonic() + timeout_seconds
    auth_header = _basic_header(username, password)
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise VerificationError("Development readiness timed out.")
        try:
            status, body = _http_request(
                f"{base_url}/health/ready", "GET", {"Authorization": auth_header}, None,
                min(HTTP_TIMEOUT_SECONDS, remaining), opener=opener,
            )
            readiness = _json_body(status, body, 200, "Development readiness endpoint")
            if (
                readiness.get("status") == "ready"
                and readiness.get("environment") == "development"
                and readiness.get("version") == expected_version
            ):
                return
            raise VerificationError("Development readiness metadata does not match the published release.")
        except VerificationError as exc:
            # Retry only transport/HTTP readiness failures; a valid response with wrong metadata is terminal.
            if "metadata does not match" in str(exc):
                raise
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise VerificationError("Development readiness timed out.") from None
            sleep(min(2.0, remaining))


def _validate_sample_metadata(meta: object, warnings: object) -> None:
    if not isinstance(meta, dict) or meta.get("currency") != "USD":
        raise VerificationError("Sample dataset metadata is missing or not USD.")
    date_range = meta.get("date_range")
    if date_range != EXPECTED_SAMPLE_DATES:
        raise VerificationError("Sample dataset date range does not match the bundled sample.")
    if meta.get("row_count") != EXPECTED_SAMPLE_ROWS:
        raise VerificationError("Sample dataset row count does not match the bundled sample.")
    if warnings != []:
        raise VerificationError("Sample dataset returned warnings.")


def _validate_analytics(summary: object) -> None:
    if not isinstance(summary, dict):
        raise VerificationError("Sample analytics response is malformed.")
    kpis = summary.get("kpis")
    if not isinstance(kpis, dict) or any(kpis.get(key) != value for key, value in EXPECTED_SAMPLE.items()):
        raise VerificationError("Sample analytics KPIs do not match the bundled sample.")
    if not isinstance(summary.get("trend"), list) or not summary["trend"]:
        raise VerificationError("Sample analytics trend is empty.")
    if not isinstance(summary.get("top_products"), list) or not summary["top_products"]:
        raise VerificationError("Sample analytics top products are empty.")


def verify_sample_workflow(
    base_url: str,
    username: str,
    password: str,
    *,
    opener: HTTP_OPENER = urllib.request.urlopen,
) -> None:
    basic = _basic_header(username, password)
    status, body = _http_request(
        f"{base_url}/api/datasets/sample", "POST", {"Authorization": basic}, b"", HTTP_TIMEOUT_SECONDS,
        opener=opener,
    )
    created = _json_body(status, body, 201, "Sample dataset creation")
    dataset_id = created.get("dataset_id")
    token = created.get("token")
    if not isinstance(dataset_id, str) or not DATASET_ID_PATTERN.fullmatch(dataset_id):
        raise VerificationError("Sample dataset response omitted a valid dataset ID.")
    if not isinstance(token, str) or not token:
        raise VerificationError("Sample dataset response omitted its access token.")
    _mask_github_value(token)
    _mask_github_value(f"Bearer {token}")
    operation_error: VerificationError | None = None
    try:
        _validate_sample_metadata(created.get("meta"), created.get("warnings"))
        # The application validates the bearer token. Caddy routes only these dataset-ID paths
        # past its Basic Auth challenge; sample creation remains Basic Auth protected.
        bearer = {"Authorization": f"Bearer {token}"}
        status, analytics_body = _http_request(
            f"{base_url}/api/datasets/{dataset_id}/analytics", "GET", bearer, None,
            HTTP_TIMEOUT_SECONDS, opener=opener,
        )
        _validate_analytics(_json_body(status, analytics_body, 200, "Sample analytics"))
    except VerificationError as exc:
        operation_error = exc

    try:
        status, _ = _http_request(
            f"{base_url}/api/datasets/{dataset_id}", "DELETE", {"Authorization": f"Bearer {token}"},
            None, HTTP_TIMEOUT_SECONDS, opener=opener,
        )
        if status != 204:
            raise VerificationError(f"Temporary sample dataset cleanup returned HTTP {status}.")
    except VerificationError as cleanup_error:
        if operation_error is not None:
            raise VerificationError(f"{operation_error}; temporary sample cleanup also failed.") from None
        raise cleanup_error
    if operation_error is not None:
        raise operation_error


def write_summary(path: Path, hostname: str, digest: str, version: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as summary:
            summary.write("## Development deployment verification\n\n")
            summary.write("- Environment: development\n")
            summary.write(f"- Hostname: `{hostname}`\n")
            summary.write(f"- Release version: `{version}`\n")
            summary.write(f"- Image digest: `sha256:{digest}`\n")
            summary.write("- Readiness: ready\n")
            summary.write("- Sample dataset: created, analytics verified, and deleted\n")
            summary.write("- Result: PASS\n")
    except OSError as exc:
        raise VerificationError(f"Unable to write verification summary ({type(exc).__name__}).") from None


def verify_deployment(
    inputs: VerificationInputs,
    *,
    runner: AWS_RUNNER = subprocess.run,
    opener: HTTP_OPENER = urllib.request.urlopen,
    summary_path: Path | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    validate_inputs(inputs)
    actual_digest, actual_version = read_deployed_release(inputs.region, runner=runner)
    expected_digest = inputs.expected_digest.removeprefix("sha256:")
    if actual_digest != expected_digest or actual_version != inputs.expected_version:
        raise VerificationError("osa-dev release metadata does not match the published image.")
    username, password = read_smoke_credential(inputs.region, runner=runner)
    base_url = f"https://{inputs.hostname}"
    wait_until_ready(
        base_url, username, password, actual_version, timeout_seconds=timeout_seconds,
        opener=opener, monotonic=monotonic, sleep=sleep,
    )
    verify_sample_workflow(base_url, username, password, opener=opener)
    if summary_path is not None:
        write_summary(summary_path, inputs.hostname, actual_digest, actual_version)


def inputs_from_environment(environment: dict[str, str] | None = None) -> VerificationInputs:
    env = os.environ if environment is None else environment
    return VerificationInputs(
        region=env.get("AWS_REGION", ""),
        hostname=env.get("OSA_DEV_HOSTNAME", ""),
        expected_digest=env.get("EXPECTED_IMAGE_DIGEST", ""),
        expected_version=env.get("EXPECTED_RELEASE_VERSION", ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    try:
        inputs = inputs_from_environment()
        validate_inputs(inputs)
        if not args.validate_only:
            verify_deployment(
                inputs,
                summary_path=Path(summary) if summary else None,
            )
    except VerificationError as exc:
        print(f"Development verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
