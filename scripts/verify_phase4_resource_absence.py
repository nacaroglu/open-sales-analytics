#!/usr/bin/env python3
"""Read-only, fail-closed verifier for Phase 4 AWS resource absence.

AWS CLI is used as the installed AWS client so this verifier adds no runtime dependency.
All discovery calls are injected through ``runner`` for offline tests.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]
REGION_RE = re.compile(r"^[a-z]{2}(?:-gov|-iso|-isob)?-[a-z]+-\d$")
REPOSITORY_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
STACKS = ("osa-dev", "osa-prod", "osa-observability", "osa-foundation")
RESOURCE_CATEGORIES = (
    "CloudFormation stacks",
    "EC2 instances",
    "EBS volumes",
    "Elastic IPs",
    "EBS snapshots",
    "SSM parameters",
    "OSA IAM roles",
    "ECR repositories and images",
    "Route 53 records",
)
STACK_ABSENCE_ERR_RE = re.compile(r"\(ValidationError\).*does not exist", re.I)
PROJECT = "open-sales-analytics"


class VerificationError(RuntimeError):
    """A safe-to-print verifier failure with no AWS response content."""

    def __init__(
        self,
        message: str,
        *,
        service_code: str | None = None,
        checked_stacks: Sequence[str] = (),
        checked_categories: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.service_code = service_code
        self.checked_stacks = tuple(checked_stacks)
        self.checked_categories = tuple(checked_categories)


def _invoke(runner: Runner, args: Sequence[str], *, region: str) -> dict[str, Any]:
    try:
        result = runner(
            ["aws", *args, "--region", region, "--output", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError(f"AWS query failed ({type(exc).__name__}).") from None
    if result.returncode:
        raise VerificationError(
            "AWS query failed; access, throttling, and service errors are not proof of absence.",
            service_code=_aws_error_code(result.stderr or ""),
        )
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        raise VerificationError("AWS query returned malformed data.") from None
    if not isinstance(payload, dict):
        raise VerificationError("AWS query returned malformed data.")
    return payload


def _aws_error_code(stderr: str) -> str | None:
    match = re.search(r"\(([A-Za-z][A-Za-z0-9]+)\)", stderr)
    return match.group(1) if match else None


def _pages(runner: Runner, base: Sequence[str], key: str, *, region: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    token: str | None = None
    seen: set[str] = set()
    while True:
        args = [*base, "--no-paginate"]
        if token is not None:
            args.extend(("--starting-token", token))
        payload = _invoke(runner, args, region=region)
        page = payload.get(key)
        if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
            raise VerificationError("AWS query returned an incomplete resource listing.")
        results.extend(page)
        token_value = payload.get("NextToken", payload.get("nextToken"))
        if key == "Roles":
            truncated = payload.get("IsTruncated")
            if not isinstance(truncated, bool):
                raise VerificationError("AWS query returned an incomplete resource listing.")
            if truncated and not isinstance(payload.get("Marker"), str):
                raise VerificationError("AWS query returned an incomplete resource listing.")
            if not truncated:
                token_value = None
        if token_value is None and payload.get("IsTruncated") is True:
            token_value = payload.get("Marker")
            if token_value is None:
                raise VerificationError("AWS query returned an incomplete resource listing.")
        if token_value is None or token_value == "":
            return results
        if not isinstance(token_value, str) or token_value in seen:
            raise VerificationError("AWS query returned an invalid pagination token.")
        seen.add(token_value)
        token = token_value


def _owned(tags: object, stack: str) -> bool:
    if not isinstance(tags, list):
        raise VerificationError("AWS query returned malformed ownership metadata.")
    values: dict[str, str] = {}
    for tag in tags:
        key, value = (
            (tag.get("Key", tag.get("key")), tag.get("Value", tag.get("value")))
            if isinstance(tag, dict)
            else (None, None)
        )
        if not isinstance(key, str) or not isinstance(value, str):
            raise VerificationError("AWS query returned malformed ownership metadata.")
        values[key] = value
    return values.get("Project") == PROJECT and values.get("OSAStack") == stack


def _ec2_tags(item: dict[str, Any]) -> list[dict[str, str]]:
    tags = item.get("Tags")
    if not isinstance(tags, list):
        raise VerificationError("AWS query returned malformed ownership metadata.")
    return tags


def _stack_absent(runner: Runner, stack: str, region: str) -> bool:
    try:
        result = runner(
            [
                "aws",
                "cloudformation",
                "describe-stacks",
                "--stack-name",
                stack,
                "--region",
                region,
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError(f"CloudFormation query failed ({type(exc).__name__}).") from None
    if result.returncode:
        if STACK_ABSENCE_ERR_RE.search(result.stderr or ""):
            return True
        raise VerificationError("CloudFormation query failed; absence could not be established.")
    try:
        payload = json.loads(result.stdout)
        stacks = payload["Stacks"]
    except (json.JSONDecodeError, TypeError, KeyError):
        raise VerificationError("CloudFormation returned malformed stack data.") from None
    if not isinstance(stacks, list) or any(not isinstance(s, dict) for s in stacks):
        raise VerificationError("CloudFormation returned malformed stack data.")
    return not stacks


def discover(
    runner: Runner,
    region: str,
    repository: str,
    *,
    checked_stacks: list[str] | None = None,
    checked_categories: list[str] | None = None,
) -> dict[str, int]:
    categories: dict[str, int] = dict.fromkeys(RESOURCE_CATEGORIES, 0)
    stacks_checked = checked_stacks if checked_stacks is not None else []
    checked = checked_categories if checked_categories is not None else []

    def mark_stack(stack: str) -> None:
        if stack not in stacks_checked:
            stacks_checked.append(stack)

    def mark_checked(category: str) -> None:
        if category not in checked:
            checked.append(category)

    for stack in STACKS:
        absent = _stack_absent(runner, stack, region)
        mark_stack(stack)
        if not absent:
            categories["CloudFormation stacks"] = categories.get("CloudFormation stacks", 0) + 1
    mark_checked("CloudFormation stacks")

    for category, operation, collection in (
        ("EC2 instances", "describe-instances", "Reservations"),
        ("EBS volumes", "describe-volumes", "Volumes"),
        ("Elastic IPs", "describe-addresses", "Addresses"),
    ):
        for stack in STACKS:
            filters = [f"Name=tag:Project,Values={PROJECT}", f"Name=tag:OSAStack,Values={stack}"]
            groups = _pages(
                runner,
                ["ec2", operation, "--filters", *filters],
                collection,
                region=region,
            )
            if collection == "Reservations":
                if any(
                    not isinstance(group.get("Instances"), list)
                    or any(not isinstance(item, dict) for item in group["Instances"])
                    for group in groups
                ):
                    raise VerificationError("AWS query returned an incomplete resource listing.")
                items = [item for group in groups for item in group["Instances"]]
            else:
                items = groups
            items = [item for item in items if _owned(_ec2_tags(item), stack)]
            categories[category] = categories.get(category, 0) + len(items)
        mark_checked(category)

    for stack in STACKS:
        filters = [f"Name=tag:Project,Values={PROJECT}", f"Name=tag:OSAStack,Values={stack}"]
        snapshots = _pages(
            runner,
            ["ec2", "describe-snapshots", "--owner-ids", "self", "--filters", *filters],
            "Snapshots",
            region=region,
        )
        categories["EBS snapshots"] = categories.get("EBS snapshots", 0) + sum(
            _owned(_ec2_tags(item), stack) for item in snapshots
        )
    mark_checked("EBS snapshots")

    for stack in STACKS:
        filters = [f"Name=tag:Project,Values={PROJECT}", f"Name=tag:OSAStack,Values={stack}"]
        parameters = _pages(
            runner,
            [
                "ssm",
                "describe-parameters",
                "--parameter-filters",
                f"Key=tag:Project,Option=Equals,Values={PROJECT}",
                f"Key=tag:OSAStack,Option=Equals,Values={stack}",
            ],
            "Parameters",
            region=region,
        )
        for parameter in parameters:
            name = parameter.get("Name")
            if not isinstance(name, str):
                raise VerificationError("SSM returned malformed parameter metadata.")
            tagged = _invoke(
                runner,
                [
                    "ssm",
                    "list-tags-for-resource",
                    "--resource-type",
                    "Parameter",
                    "--resource-id",
                    name,
                ],
                region=region,
            )
            if not _owned(tagged.get("TagList"), stack):
                # Server-side tag filters identify the exact ownership scope. A missing owner tag
                # is treated as incomplete service data rather than silently accepted.
                raise VerificationError("SSM returned incomplete ownership metadata.")
            categories["SSM parameters"] = categories.get("SSM parameters", 0) + 1
    mark_checked("SSM parameters")

    for stack in STACKS:
        roles = _pages(
            runner,
            ["iam", "list-roles", "--path-prefix", f"/{stack}/"],
            "Roles",
            region=region,
        )
        categories["OSA IAM roles"] = categories.get("OSA IAM roles", 0) + sum(
            _owned(role.get("Tags"), stack) for role in roles
        )
    mark_checked("OSA IAM roles")

    try:
        repos = _pages(
            runner,
            ["ecr", "describe-repositories", "--repository-names", repository],
            "repositories",
            region=region,
        )
    except VerificationError as exc:
        if exc.service_code == "RepositoryNotFoundException":
            repos = []
        else:
            raise
    if len(repos) > 1:
        raise VerificationError("ECR returned malformed repository data.")
    owned_repo = False
    if repos:
        arn = repos[0].get("repositoryArn")
        if not isinstance(arn, str):
            raise VerificationError("ECR returned malformed repository data.")
        tags = _pages(
            runner, ["ecr", "list-tags-for-resource", "--resource-arn", arn], "tags", region=region
        )
        if len(tags) != 1:
            raise VerificationError("ECR returned malformed ownership metadata.")
        owned_repo = _owned(tags[0], "osa-foundation")
    image_count = 0
    if owned_repo:
        images = _pages(
            runner,
            ["ecr", "list-images", "--repository-name", repository],
            "imageIds",
            region=region,
        )
        image_count = len(images)
    categories["ECR repositories and images"] = int(owned_repo) + image_count
    mark_checked("ECR repositories and images")

    # Phase 4 templates do not declare Route 53 record sets. DNS records are operator-owned
    # inputs (hostnames are parameters), so no hosted zone or record is in the ownership scope.
    mark_checked("Route 53 records")
    return categories


def verify(
    region: str,
    *,
    runner: Runner = subprocess.run,
    timeout_seconds: float = 120,
    poll_seconds: float = 5,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    repository: str = "open-sales-analytics",
) -> dict[str, Any]:
    if not REGION_RE.fullmatch(region):
        raise VerificationError("AWS region is missing or malformed.")
    if (
        not math.isfinite(timeout_seconds)
        or not math.isfinite(poll_seconds)
        or timeout_seconds <= 0
        or poll_seconds <= 0
    ):
        raise VerificationError("Polling bounds must be positive.")
    if not REPOSITORY_RE.fullmatch(repository) or len(repository) > 256:
        raise VerificationError("ECR repository name is missing or malformed.")
    deadline = monotonic() + timeout_seconds
    checked_stacks: list[str] = []
    checked_categories: list[str] = []
    while True:
        try:
            counts = discover(
                runner,
                region,
                repository,
                checked_stacks=checked_stacks,
                checked_categories=checked_categories,
            )
        except VerificationError as exc:
            raise VerificationError(
                str(exc),
                service_code=exc.service_code,
                checked_stacks=checked_stacks,
                checked_categories=checked_categories,
            ) from None
        if not any(counts.values()):
            return {
                "verified_at_utc": datetime.now(UTC).isoformat(),
                "region": region,
                "target_stacks": list(STACKS),
                "checked_stacks": checked_stacks.copy(),
                "categories": counts,
                "result": "PASS",
            }
        remaining = deadline - monotonic()
        if remaining <= 0:
            remaining_categories = ", ".join(name for name, count in counts.items() if count)
            raise VerificationError(
                f"Timed out; resources remain in categories: {remaining_categories}.",
                checked_stacks=checked_stacks,
                checked_categories=checked_categories,
            )
        sleep(min(poll_seconds, remaining))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    )
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--repository", default="open-sales-analytics")
    args = parser.parse_args(argv)
    try:
        report = verify(
            args.region or "",
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            repository=args.repository,
        )
    except VerificationError as exc:
        print(
            json.dumps(
                {
                    "verified_at_utc": datetime.now(UTC).isoformat(),
                    "region": args.region or "unset",
                    "target_stacks": list(STACKS),
                    "checked_stacks": list(exc.checked_stacks),
                    "checked_categories": list(exc.checked_categories),
                    "result": "FAIL",
                    "error": str(exc),
                }
            )
        )
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
