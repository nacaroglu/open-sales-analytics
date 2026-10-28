#!/usr/bin/env python3
"""Offline structural checks for the guarded Phase 4 teardown workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/teardown-phase4.yml"
SCRIPT = ROOT / "scripts/teardown_phase4.py"
ENVIRONMENT_CHECKER = ROOT / "scripts/verify_phase4_environment.py"
DOC = ROOT / "deploy/README.md"


def main() -> int:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    environment_checker = ENVIRONMENT_CHECKER.read_text(encoding="utf-8")
    docs = DOC.read_text(encoding="utf-8")
    required_workflow = (
        "workflow_dispatch:",
        "environment: osa-teardown",
        "inputs.mode == 'dry-run'",
        "inputs.mode == 'execute'",
        "preflight:",
        "run: python3 scripts/teardown_phase4.py --preflight-only",
        "vars.OSA_TEARDOWN_PREFLIGHT_ROLE_ARN",
        '[[ "$CONFIRMATION" == "DELETE-PHASE4-OSA-RESOURCES" ]]',
        "aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd",
        "python3 scripts/teardown_phase4.py --dry-run",
        'python3 scripts/teardown_phase4.py --execute --confirm "$CONFIRMATION"',
        "GITHUB_STEP_SUMMARY",
        "Safe failure stage: `workflow_setup`",
        "if: always()",
    )
    if any(fragment not in workflow for fragment in required_workflow):
        raise SystemExit("teardown workflow is missing a required dispatch or guard")
    if "pull_request:" in workflow or "push:" in workflow:
        raise SystemExit("teardown workflow must not run from ordinary CI or pushes")
    if "github.ref == 'refs/heads/main'" not in workflow:
        raise SystemExit("teardown workflow must be restricted to main")
    required_script = (
        '"osa-dev", "osa-prod", "osa-observability", "osa-foundation"',
        '"delete-stack"',
        '"stack-delete-complete"',
        '"list-imports"',
        '"get-caller-identity"',
        "Later stacks were not touched.",
    )
    if any(fragment not in script for fragment in required_script):
        raise SystemExit("teardown script is missing a required safety guard")
    if "delete-resource" in script or "delete-snapshot" in script:
        raise SystemExit("teardown must delegate resource deletion to CloudFormation")
    if (
        '"required_reviewers"' not in environment_checker
        or "verify_phase4_environment.py" not in docs
    ):
        raise SystemExit("teardown reviewer protection verification is missing")
    print("Phase 4 teardown workflow structure is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
