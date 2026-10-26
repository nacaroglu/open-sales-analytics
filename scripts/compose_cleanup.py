#!/usr/bin/env python3
"""Remove only Compose projects backed by verified local Make-run markers."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

TEMP_ROOT_PATTERN = re.compile(
    r"^(?P<scope>[a-z0-9][a-z0-9_-]*)-(?P<kind>integration|e2e)-"
    r"(?P<run_id>[0-9a-f]{8})-work$"
)
TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OWNER_MARKER = ".osa-compose-owner"


def run(args: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True, env=env)
    return result.stdout.strip()


def compose_projects() -> set[str]:
    resources = (
        (
            ["docker", "container", "ls", "-aq", "--filter", "label=com.docker.compose.project"],
            ["docker", "container", "inspect", "--format", "{{json .Config.Labels}}"],
        ),
        (
            ["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project"],
            ["docker", "volume", "inspect", "--format", "{{json .Labels}}"],
        ),
        (
            ["docker", "network", "ls", "-q", "--filter", "label=com.docker.compose.project"],
            ["docker", "network", "inspect", "--format", "{{json .Labels}}"],
        ),
    )
    projects: set[str] = set()
    for listing, inspect in resources:
        for resource_id in run(listing).splitlines():
            labels = json.loads(run([*inspect, resource_id]))
            if labels:
                project = labels.get("com.docker.compose.project")
                if project:
                    projects.add(project)
    return projects


def verified_temp_root(
    path: Path,
    scope: str,
    expected_kind: str | None = None,
    expected_token: str | None = None,
) -> dict | None:
    if path.parent != Path("/tmp"):
        return None
    match = TEMP_ROOT_PATTERN.fullmatch(path.name)
    if not match or match.group("scope") != scope:
        return None
    if expected_kind is not None and match.group("kind") != expected_kind:
        return None
    try:
        root_stat = path.lstat()
        marker = path / OWNER_MARKER
        marker_stat = marker.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(root_stat.st_mode) or path.is_symlink() or root_stat.st_uid != os.getuid():
        return None
    if stat.S_IMODE(root_stat.st_mode) & 0o077:
        return None
    if not stat.S_ISREG(marker_stat.st_mode) or marker.is_symlink() or marker_stat.st_uid != os.getuid():
        return None
    if stat.S_IMODE(marker_stat.st_mode) & 0o077:
        return None
    try:
        owner = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(owner, dict):
        return None
    token = owner.get("token")
    if (
        set(owner) != {"scope", "run_id", "kind", "token"}
        or owner["scope"] != scope
        or owner["run_id"] != match.group("run_id")
        or owner["kind"] != match.group("kind")
        or not isinstance(token, str)
        or TOKEN_PATTERN.fullmatch(token) is None
        or (expected_token is not None and token != expected_token)
    ):
        return None
    return owner


def discover_owned_runs(scope: str) -> list[tuple[Path, dict]]:
    runs: list[tuple[Path, dict]] = []
    patterns = (f"{scope}-integration-*-work", f"{scope}-e2e-*-work")
    for pattern in patterns:
        for path in sorted(Path("/tmp").glob(pattern)):
            owner = verified_temp_root(path, scope)
            if owner is None:
                raise RuntimeError(f"Refusing to trust or remove unverified test directory: {path}")
            runs.append((path, owner))
    return runs


def project_names(scope: str, owner: dict) -> set[str]:
    run_id = owner["run_id"]
    if owner["kind"] == "integration":
        prefix = f"{scope}-integration-{run_id}"
        return {f"{prefix}-selfhost", f"{prefix}-demo"}
    return {f"{scope}-e2e-{run_id}"}


def clean_compose_projects(scope: str, owned_projects: dict[str, str]) -> None:
    existing = compose_projects()
    for project, kind in sorted(owned_projects.items()):
        if project not in existing:
            continue
        files = ["docker-compose.yaml"]
        if kind == "integration":
            files.extend(
                [
                    "docker-compose.integration-test.yaml",
                    "docker-compose.test-telemetry.yaml",
                ]
            )
        else:
            files.append("docker-compose.integration-test.yaml")
        command = ["docker", "compose", "--project-name", project]
        for compose_file in files:
            command.extend(["-f", compose_file])
        environment = os.environ.copy()
        environment["OSA_TEST_TELEMETRY_DIR"] = f"/tmp/{scope}-clean-placeholder"
        subprocess.run(
            [*command, "down", "--volumes", "--remove-orphans"],
            check=True,
            env=environment,
        )

    remaining = compose_projects().intersection(owned_projects)
    if remaining:
        names = ", ".join(sorted(remaining))
        raise RuntimeError(f"Compose resources remain for verified Make runs: {names}")


def remove_verified_root(path: Path, owner: dict) -> None:
    shutil.rmtree(path)


def clean_owned_runs(scope: str, runs: list[tuple[Path, dict]]) -> None:
    owned_projects: dict[str, str] = {}
    for _, owner in runs:
        for project in project_names(scope, owner):
            owned_projects[project] = owner["kind"]
    clean_compose_projects(scope, owned_projects)
    for path, owner in runs:
        if verified_temp_root(path, scope, owner["kind"], owner["token"]) is None:
            raise RuntimeError(f"Temporary test directory ownership changed during cleanup: {path}")
        remove_verified_root(path, owner)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--token")
    parser.add_argument("--kind", choices=("integration", "e2e"))
    args = parser.parse_args()
    scope = os.environ.get("OSA_PROJECT_SCOPE", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", scope):
        parser.error("OSA_PROJECT_SCOPE must be a short, safe project identifier")

    if args.temp_root is not None:
        if not args.token or not args.kind or TOKEN_PATTERN.fullmatch(args.token) is None:
            parser.error("--temp-root cleanup requires its kind and 128-bit owner token")
        owner = verified_temp_root(args.temp_root, scope, args.kind, args.token)
        if owner is None:
            raise RuntimeError(f"Refusing to clean unverified temporary test directory: {args.temp_root}")
        clean_owned_runs(scope, [(args.temp_root, owner)])
    else:
        clean_owned_runs(scope, discover_owned_runs(scope))
    print("Owned integration/E2E Compose resources and verified telemetry sinks are clean.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
