"""Guard required, independently scheduled pull-request CI checks."""

from __future__ import annotations

import re
import sys
from pathlib import Path


WORKFLOW = Path(".github/workflows/ci.yml")
MAKEFILE = Path("Makefile")
FOUNDATION_VALIDATOR = Path("scripts/validate_foundation_template.py")
APPLICATION_VALIDATOR = Path("scripts/validate_application_template.py")
MANIFEST_VALIDATOR = Path("scripts/validate_environment_manifests.py")
REQUIRED_COMMANDS = {
    "backend-tests": (
        "uv run pytest",
        "uv run ruff check backend",
        "uv run ruff format --check backend",
        "uv run mypy backend/app",
    ),
    "frontend": (
        "npm test",
        "npm run lint",
        "npm run typecheck",
        "npm run build",
    ),
}
CONTAINER_CHECKS = (
    'docker build --build-arg OSA_VERSION=',
    'org.opencontainers.image.version',
    '[[ "$label" =~ ^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$ ]]',
    'runtime-override',
    'Verify the runtime image contains only production artifacts',
    'docker-compose.integration-test.yaml up --detach --no-build',
    'curl -f http://localhost:8000/api/health',
    "grep -qi '<div id=\"root\"'",
    'Wait for Docker health status',
    'run: make e2e',
)


def fail(message: str) -> None:
    print(f"CI parallelism validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def top_level_section(source: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}:\s*$", source)
    if match is None:
        fail(f"workflow is missing top-level {name!r}")
    next_section = re.search(r"(?m)^[A-Za-z][\w-]*:\s*$", source[match.end() :])
    end = match.end() + next_section.start() if next_section else len(source)
    return source[match.end() : end]


def job_blocks(jobs: str) -> dict[str, str]:
    starts = list(re.finditer(r"(?m)^  ([a-zA-Z0-9_-]+):\s*$", jobs))
    blocks = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(jobs)
        blocks[match.group(1)] = jobs[match.end() : end]
    return blocks


def validate() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    triggers = top_level_section(source, "on")
    if not re.search(r"(?m)^  pull_request:\s*(?:#.*)?$", triggers):
        fail("workflow must run for pull requests")

    permissions = top_level_section(source, "permissions")
    permission_entries = re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):\s*([^\s#]+)", permissions)
    if permission_entries != [("contents", "read")]:
        fail("pull request workflow permissions must remain contents: read only")

    jobs = job_blocks(top_level_section(source, "jobs"))
    for name, commands in REQUIRED_COMMANDS.items():
        block = jobs.get(name)
        if block is None:
            fail(f"required independent job {name!r} is missing")
        if re.search(r"(?m)^    needs\s*:", block):
            fail(f"job {name!r} has a needs dependency and may be serialized")
        for command in commands:
            if command not in block:
                fail(f"job {name!r} is missing required check {command!r}")

    structure_job = jobs.get("ci-structure", "")
    if "python3 scripts/validate_ci_parallelism.py" not in structure_job:
        fail("the workflow structure regression check must remain enabled")

    container = jobs.get("docker-smoke")
    if container is None:
        fail("the production image and browser job 'docker-smoke' is missing")
    for check in CONTAINER_CHECKS:
        if check not in container:
            fail(f"docker-smoke is missing required image/browser check {check!r}")
    for cleanup_check in (
        "name: Remove Compose app and test data",
        "if: always()",
        'down --volumes --remove-orphans || cleanup_status=1',
        'Browser Compose containers remain after cleanup',
        'Browser Compose volumes remain after cleanup',
    ):
        if cleanup_check not in container:
            fail(f"docker-smoke is missing failure-safe cleanup check {cleanup_check!r}")

    integration = jobs.get("compose-integration")
    if integration is None:
        fail("the dedicated 'compose-integration' job is missing")
    for check in (
        "Validate integration Compose configuration",
        "docker-compose.integration-test.yaml",
        "docker-compose.test-telemetry.yaml config --quiet",
        "run: make integration",
    ):
        if check not in integration:
            fail(f"compose-integration is missing required check {check!r}")

    makefile = MAKEFILE.read_text(encoding="utf-8")
    for target in ("integration", "e2e"):
        target_block = re.search(
            rf"(?ms)^{target}:\n(?P<body>.*?)(?=^[A-Za-z][A-Za-z0-9_-]*:|\Z)", makefile
        )
        if target_block is None:
            fail(f"Makefile target {target!r} is missing")
        body = target_block.group("body")
        if "trap cleanup EXIT" not in body or "scripts/compose_cleanup.py" not in body:
            fail(f"Makefile target {target!r} must run owned-resource cleanup on success and failure")
        if f"--kind {target}" not in body:
            fail(f"Makefile target {target!r} must identify its test resources to cleanup")
        if target == "e2e" and "up --build --detach" not in body:
            fail("make e2e must retain its independent Compose lifecycle")

    cleanup_script = Path("scripts/compose_cleanup.py").read_text(encoding="utf-8")
    for behavior in (
        '["docker", "container", "ls", "-aq", "--filter", "label=com.docker.compose.project"]',
        '["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project"]',
        '["docker", "network", "ls", "-q", "--filter", "label=com.docker.compose.project"]',
        '"down", "--volumes", "--remove-orphans"',
        "remaining = compose_projects().intersection(owned_projects)",
        "verified_temp_root(path, scope, owner[\"kind\"], owner[\"token\"])",
        "shutil.rmtree(path)",
    ):
        if behavior not in cleanup_script:
            fail(f"Compose cleanup must keep container/network/volume/temp-data handling ({behavior})")

    cloudformation = jobs.get("cloudformation-foundation")
    if cloudformation is None:
        fail("the dedicated 'cloudformation-foundation' job is missing")
    if re.search(r"(?m)^    permissions\s*:", cloudformation):
        fail("cloudformation-foundation must inherit the workflow's read-only permissions")
    for check in (
        "Install and verify pinned AWS cfn-validate",
        "Validate CloudFormation schemas offline",
        "cfn-validate --strict deploy/cloudformation/osa-foundation.yaml",
        (
            "cfn-validate --strict deploy/cloudformation/osa-application.yaml \\\n"
            "            --exclude-resource-id AppInstance=W9010 \\\n"
            "            --parameter Environment=development"
        ),
        (
            "cfn-validate --strict deploy/cloudformation/osa-application.yaml \\\n"
            "            --exclude-resource-id AppInstance=W9010 \\\n"
            "            --parameter Environment=production"
        ),
        "python3 scripts/validate_foundation_template.py",
        "python3 scripts/validate_application_template.py",
        "python3 scripts/validate_environment_manifests.py",
    ):
        if check not in cloudformation:
            fail(f"cloudformation-foundation is missing required check {check!r}")

    for integrity_check in (
        "version=1.14.0",
        'base="https://github.com/aws-cloudformation/cloudformation-validate/releases/download/${version}"',
        'curl --fail --silent --show-error --location "$base/$asset.sig" --output "$asset.sig"',
        'curl --fail --silent --show-error --location "$base/signing-key.pem" --output signing-key.pem',
        "printf '%s  %s\\n' 'e63674a37a2431a85d637326e959c1717af01b4768734a5cb0bf79ef8652ece2' \"$asset\" | sha256sum --check --strict",
        "printf '%s  %s\\n' 'f0a7827e53764081deda3d363126e7c67dfb4844bd4db5f2d3fe42c713e064d0' signing-key.pem | sha256sum --check --strict",
        'openssl dgst -sha256 -verify signing-key.pem -signature "$asset.sig" "$asset"',
    ):
        if integrity_check not in cloudformation:
            fail(f"cloudformation-foundation is missing release integrity check {integrity_check!r}")

    lowered_cloudformation = cloudformation.lower()
    for forbidden in (
        "secrets.",
        "configure-aws-credentials",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
    ):
        if forbidden in lowered_cloudformation:
            fail(f"cloudformation-foundation must remain offline/read-only and must not use {forbidden!r}")
    if re.search(r"\baws\s+(?:cloudformation|ec2|iam|ecr|ssm)\b", lowered_cloudformation):
        fail("cloudformation-foundation must not invoke AWS resource or identity commands")

    security_markers = {
        FOUNDATION_VALIDATOR: (
            "OIDC subject must be exact owner/repository/branch without wildcard",
            "def exact_trust(",
            'exact_trust("BuildRole", "github", branch_subject)',
            "trust must be limited to",
            "Resource:*",
            "security groups or ingress rules",
        ),
        APPLICATION_VALIDATOR: (
            "security group must declare exactly HTTP and HTTPS ingress",
            "for forbidden_port in (22, 4317, 4318)",
            "outputs must contain only stable non-secret release/runtime verification values",
        ),
        MANIFEST_VALIDATOR: (
            "must resolve to the shared osa-application.yaml template",
            "development and production must share one template",
        ),
    }
    for path, markers in security_markers.items():
        validator_source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in validator_source:
                fail(f"{path} is missing reviewed infrastructure assertion marker {marker!r}")

    print("CI workflow structure, container/Compose coverage, and CloudFormation security validation passed")


if __name__ == "__main__":
    validate()
