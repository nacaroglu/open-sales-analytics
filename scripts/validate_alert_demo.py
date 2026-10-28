#!/usr/bin/env python3
"""Offline checks for the #269 runbook and pending evidence template."""

from __future__ import annotations

import argparse
from pathlib import Path

RUNBOOK_REQUIREMENTS = (
    "authenticated development deployment",
    "Never run against production",
    "OSARepeatedDatasetCreationFailures",
    "10-minute query window and 5-minute pending period",
    "python -m app.controlled_failure --confirm-controlled-failure",
    "three internal creation failures",
    "test webhook",
    "sample workflow",
    "bounded intervals",
    "issue #270",
)
EVIDENCE_REQUIREMENTS = (
    "**Status: Pending. No live development demonstration has been performed.**",
    "| Alert firing after pending period for development/release | Pending | Pending |",
    "| Test webhook delivery succeeded; bounded labels only | Pending | Pending |",
    "| Correlated logs captured | Pending | Pending |",
    "| Correlated trace captured | Pending | Pending |",
    "| App readiness and sample workflow recovered | Pending | Pending |",
    "| Alert resolved after failures aged out of 10m window | Pending | Pending |",
)


def validate_documents(runbook: str, evidence: str) -> list[str]:
    """Return offline documentation errors; never contacts external systems."""
    errors = [
        f"runbook missing requirement: {item}"
        for item in RUNBOOK_REQUIREMENTS
        if item not in runbook
    ]
    errors.extend(
        f"evidence missing pending row: {item}"
        for item in EVIDENCE_REQUIREMENTS
        if item not in evidence
    )
    if "AWS" not in runbook or "webhook" not in runbook:
        errors.append("runbook must identify external systems that are out of scope for offline checks")
    if "Status: Pending" not in evidence:
        errors.append("evidence must remain pending until a live operator run")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runbook", type=Path, default=Path("_docs/alert_demo_269.md"))
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("_docs/evidence/alert-demo-269.md"),
    )
    args = parser.parse_args()
    errors = validate_documents(args.runbook.read_text(), args.evidence.read_text())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("Offline alert demonstration documents are valid; live evidence remains Pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
