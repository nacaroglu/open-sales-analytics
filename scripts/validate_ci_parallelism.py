"""Guard the pull-request workflow's independent backend and frontend jobs."""

from __future__ import annotations

import re
import sys
from pathlib import Path


WORKFLOW = Path(".github/workflows/ci.yml")
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

    print("CI parallelism validation passed")


if __name__ == "__main__":
    validate()
