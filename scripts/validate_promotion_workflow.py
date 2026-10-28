#!/usr/bin/env python3
"""Offline checks for the approval-gated production promotion workflow."""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/promote-production.yml")
PROMOTION_SCRIPT = Path("scripts/promote_production.py")


def fail(message: str) -> None:
    print(f"Production promotion validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def section(source: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}:\s*$", source)
    if match is None:
        fail(f"workflow is missing {name!r}")
    next_section = re.search(r"(?m)^[A-Za-z][\w-]*:\s*$", source[match.end() :])
    end = match.end() + next_section.start() if next_section else len(source)
    return source[match.end() : end]


def validate(source: str | None = None) -> None:
    text = WORKFLOW.read_text(encoding="utf-8") if source is None else source
    promotion = PROMOTION_SCRIPT.read_text(encoding="utf-8")
    if not re.search(r"(?ms)^on:\s*\n\s+workflow_dispatch:\s*(?:\n|$)", text):
        fail("only a manual workflow_dispatch trigger is allowed")
    if "inputs:" in text or "inputs." in text:
        fail("callers must not supply a digest or version")
    permissions = section(text, "permissions")
    if not re.search(r"(?m)^  contents: read\s*$", permissions) or "id-token" in permissions:
        fail("top-level permissions must stay read-only; OIDC permission belongs to jobs")
    jobs = section(text, "jobs")
    read_match = re.search(r"(?ms)^  read-dev-release:\n(?P<body>.*?)(?=^  [\w-]+:|\Z)", jobs)
    promote_match = re.search(r"(?ms)^  promote:\n(?P<body>.*?)(?=^  [\w-]+:|\Z)", jobs)
    if read_match is None or promote_match is None:
        fail("main-only source validation and promotion jobs are required")
    read_job, promote = read_match.group("body"), promote_match.group("body")
    if (
        "if: github.ref == 'refs/heads/main'" not in read_job
        or "if: github.ref == 'refs/heads/main'" not in promote
    ):
        fail("workflow_dispatch jobs must run only from main")
    if not re.search(r"(?m)^    environment: production\s*$", promote):
        fail("production job must use the protected production Environment")
    if "needs: [read-dev-release]" not in promote:
        fail("promotion must depend on successful dev metadata validation")
    ordered = (
        (read_job, "scripts/promote_production.py --validate-only", "configure-aws-credentials"),
        (read_job, "configure-aws-credentials", "scripts/promote_production.py --read-dev"),
        (promote, "scripts/promote_production.py --validate-only", "configure-aws-credentials"),
        (promote, "configure-aws-credentials", "scripts/promote_production.py --read-dev"),
        (
            promote,
            "scripts/promote_production.py --read-dev",
            "role-to-assume: ${{ vars.OSA_PROD_PROMOTION_ROLE_ARN }}",
        ),
        (
            promote,
            "role-to-assume: ${{ vars.OSA_PROD_PROMOTION_ROLE_ARN }}",
            "scripts/promote_production.py --promote",
        ),
    )
    for job, first, second in ordered:
        if first not in job or second not in job or job.index(first) >= job.index(second):
            fail(
                f"required ordered promotion step missing or reversed: {first!r} before {second!r}"
            )
    if "role-to-assume: ${{ vars.OSA_PRODUCTION_SOURCE_READ_ROLE_ARN }}" not in read_job:
        fail("preflight must use the read-only source role")
    forbidden = (
        "aws-access-key-id:",
        "aws-secret-access-key:",
        "secrets.",
        "docker build",
        "docker push",
        "aws ecr",
        "build-push-action",
        "retag",
    )
    if any(marker in text.lower() for marker in forbidden):
        fail("workflow must not use long-lived keys or build, push, or retag images")
    rollback_contract = (
        "verifier(config, source)",
        "update_command(config, previous)",
        'verification="FAIL"',
        'rollback="PASS"',
        'rollback="FAILED"',
        'raise PromotionError("osa-prod release metadata does not match the promoted release.")',
    )
    if any(marker not in promotion for marker in rollback_contract):
        fail(
            "promotion code must verify the production release and report digest-pinned rollback outcomes"
        )


if __name__ == "__main__":
    validate()
    print("Production promotion workflow configuration is valid.")
