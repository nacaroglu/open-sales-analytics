#!/usr/bin/env python3
"""Publish a prebuilt OSA image under its immutable version and record its digest."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
VERSION_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$")
REPOSITORY_PATTERN = re.compile(
    r"^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/"
    r"[a-z0-9]+(?:[._/-][a-z0-9]+)*$"
)
DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


class PublishError(RuntimeError):
    """A publication step failed without including command output or credentials."""


def _run(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    step: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            list(command),
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise PublishError(f"{step} could not start ({type(exc).__name__}).") from None
    if result.returncode != 0:
        if step == "ECR image push":
            raise PublishError(
                f"{step} failed (exit {result.returncode}); immutable tag collisions are not overwritten."
            )
        raise PublishError(f"{step} failed (exit {result.returncode}).")
    return result


def publish_image(
    *,
    repository_uri: str,
    version: str,
    region: str,
    output_path: Path,
    runner: CommandRunner = subprocess.run,
) -> dict[str, str]:
    """Push a prebuilt image and validate its immutable ECR digest."""
    if not REPOSITORY_PATTERN.fullmatch(repository_uri):
        raise PublishError("ECR repository URI is missing or malformed.")
    if not VERSION_PATTERN.fullmatch(version):
        raise PublishError("Release version is missing or malformed.")
    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
        raise PublishError("AWS region is missing or malformed.")

    registry = repository_uri.split("/", maxsplit=1)[0]
    repository_name = repository_uri.split("/", maxsplit=1)[1]
    source_image = "open-sales-analytics"
    tagged_image = f"{repository_uri}:{version}"

    login = _run(
        runner,
        ["aws", "ecr", "get-login-password", "--region", region],
        step="ECR authentication token request",
    )
    if not login.stdout:
        raise PublishError("ECR authentication token request returned an empty token.")
    _run(
        runner,
        ["docker", "login", "--username", "AWS", "--password-stdin", registry],
        input_text=login.stdout,
        step="ECR registry login",
    )
    _run(
        runner,
        ["docker", "tag", source_image, tagged_image],
        step="Tagging the validated image",
    )
    _run(runner, ["docker", "push", tagged_image], step="ECR image push")
    lookup = _run(
        runner,
        [
            "aws",
            "ecr",
            "describe-images",
            "--region",
            region,
            "--repository-name",
            repository_name,
            "--image-ids",
            f"imageTag={version}",
            "--query",
            "imageDetails[0].imageDigest",
            "--output",
            "text",
        ],
        step="ECR digest lookup",
    )
    digest = lookup.stdout.strip()
    if not DIGEST_PATTERN.fullmatch(digest):
        raise PublishError("ECR digest lookup returned a missing or malformed SHA-256 digest.")

    outputs = {
        "repository-uri": repository_uri,
        "release-version": version,
        "digest": digest,
        "image-ref": f"{repository_uri}@{digest}",
    }
    try:
        with output_path.open("a", encoding="utf-8") as output:
            for key, value in outputs.items():
                output.write(f"{key}={value}\n")
    except OSError as exc:
        raise PublishError(
            f"Unable to record publication outputs ({type(exc).__name__})."
        ) from None
    return outputs


def main() -> int:
    try:
        output_file = os.environ.get("GITHUB_OUTPUT")
        if not output_file:
            raise PublishError(
                "GITHUB_OUTPUT is missing; refusing to publish without recording outputs."
            )
        publish_image(
            repository_uri=os.environ.get("ECR_REPOSITORY_URI", ""),
            version=os.environ.get("RELEASE_VERSION", ""),
            region=os.environ.get("AWS_REGION", ""),
            output_path=Path(output_file),
        )
    except PublishError as exc:
        print(f"ECR image publication failed: {exc}", file=sys.stderr)
        return 1
    return 0
