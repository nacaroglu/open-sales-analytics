#!/usr/bin/env python3
"""Check deployment-summary field contracts and prevent direct secret-bearing fields."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NoReturn

SUMMARY_FUNCTIONS: dict[Path, dict[str, tuple[str, ...]]] = {
    Path("scripts/deploy_dev_stack.py"): {
        "write_summary": (
            "- Environment: development",
            "- Image tag:",
            "- Release version:",
            "- Image digest:",
            "- CloudFormation deployment:",
            "- Readiness:",
            "- Sample analytics smoke:",
            "- Temporary sample cleanup:",
            "- CloudFormation rollback:",
            "- Failure stage:",
            "- Result:",
        )
    },
    Path("scripts/verify_dev_deployment.py"): {
        "write_summary": (
            "- Environment: development",
            "- Image tag:",
            "- Release version:",
            "- Image digest:",
            "- CloudFormation deployment: PASS",
            "- Readiness:",
            "- Sample analytics smoke:",
            "- Temporary sample cleanup:",
            "- Failure stage:",
            "- Result:",
        )
    },
    Path("scripts/promote_production.py"): {
        "write_summary": (
            "- Environment: production",
            "- Image tag:",
            "- Release version:",
            "- Image digest:",
            "- Previous production image tag:",
            "- Previous production version:",
            "- Previous production digest:",
            "- Readiness:",
            "- Sample analytics smoke:",
            "- Temporary sample cleanup:",
            "- Production verification:",
            "- Rollback:",
            "- Failure stage:",
            "- Rollback failure stage:",
            "- Result:",
        )
    },
}

FORBIDDEN_SUMMARY_IDENTIFIERS = {
    "hostname",
    "account",
    "password",
    "token",
    "stdout",
    "stderr",
    "authorization",
}


def fail(message: str) -> NoReturn:
    print(f"Deployment evidence validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate() -> None:
    for path, functions in SUMMARY_FUNCTIONS.items():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for function_name, required in functions.items():
            node = next(
                (
                    child
                    for child in tree.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name == function_name
                ),
                None,
            )
            if node is None:
                fail(f"{path} is missing {function_name}()")
            function_source = ast.get_source_segment(source, node) or ""
            missing = [marker for marker in required if marker not in function_source]
            if missing:
                fail(f"{path} {function_name}() omits required evidence fields: {missing!r}")
            identifiers = {
                child.id.lower() for child in ast.walk(node) if isinstance(child, ast.Name)
            }
            identifiers.update(
                child.attr.lower() for child in ast.walk(node) if isinstance(child, ast.Attribute)
            )
            exposed = sorted(identifiers & FORBIDDEN_SUMMARY_IDENTIFIERS)
            if exposed:
                fail(f"{path} {function_name}() references sensitive fields: {exposed!r}")


if __name__ == "__main__":
    validate()
    print("Deployment evidence fields and redaction contract passed.")
