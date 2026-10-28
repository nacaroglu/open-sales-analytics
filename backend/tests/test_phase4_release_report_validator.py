from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_phase4_release_report.py"
REPORT_PATH = ROOT / "_docs" / "phase-4-release-report.md"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
SPEC = importlib.util.spec_from_file_location("validate_phase4_release_report", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

LABELS = validator.ENTRY_LABELS
NOW = "2026-10-28T04:32:07Z"


def make_report(
    *, status: str = "Incomplete", pending_action: str = "Run the approved operator workflow."
) -> str:
    sections = [
        "# Phase 4 release evidence report",
        "",
        f"Overall status: {status} — live evidence remains pending.",
        "",
    ]
    for index, label in enumerate(LABELS, start=1):
        complete = index == 1
        sections.extend(
            [
                f"## {index}. {label}",
                f"Evidence status: {'Complete' if complete else 'Pending — evidence has not been captured.'}",
                "Source: [evidence source](https://example.invalid/evidence)",
                f"Evidence captured at (UTC): {NOW if complete else 'Pending — capture after the evidence is produced.'}",
                f"Status checked at (UTC): {NOW}",
                "Environment: CI" if complete else "Environment: Development",
                "Release/version: `abc1234`"
                if complete
                else "Release/version: Pending — no release is deployed.",
                "Evidence type: Automated" if complete else "Evidence type: Live",
            ]
        )
        if not complete:
            sections.append(f"Operator action: {pending_action}")
        sections.append("")
    return "\n".join(sections)


def test_checked_in_report_has_all_eleven_valid_entries() -> None:
    errors = validator.validate_report_text(REPORT_PATH.read_text(encoding="utf-8"))

    assert errors == []


def test_rollback_entry_links_the_verified_automated_test() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    section = report.partition("## 9. Rollback demonstration or automated rollback test")[2]
    section = section.partition("## 10.")[0]

    assert "Evidence status: Complete" in section
    assert "pull/315" in section
    assert "actions/runs/40567977259" in section
    assert "Environment: GitHub Actions CI" in section
    assert "50a8f2b4954b16ff16136f8d2aaaded3704f52ef" in section
    assert "Evidence type: Automated" in section
    assert "no live production rollback was performed" in section


def test_ci_runs_the_offline_report_validator() -> None:
    workflow = CI_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python3 scripts/validate_phase4_release_report.py" in workflow


def test_report_requires_all_eleven_labeled_entries() -> None:
    report = make_report().replace("## 11. ", "## 12. ", 1)

    errors = validator.validate_report_text(report)

    assert any("11" in error and "entry" in error.lower() for error in errors)


def test_pending_evidence_requires_reason_and_operator_action() -> None:
    report = make_report().replace("Operator action: Run the approved operator workflow.\n", "", 1)

    errors = validator.validate_report_text(report)

    assert any("operator action" in error.lower() for error in errors)


def test_pending_entries_cannot_be_reported_as_complete() -> None:
    report = make_report(status="Complete")

    errors = validator.validate_report_text(report)

    assert any("pending" in error.lower() and "incomplete" in error.lower() for error in errors)


def test_complete_evidence_requires_a_valid_utc_capture_time() -> None:
    report = make_report().replace(
        f"Evidence captured at (UTC): {NOW}", "Evidence captured at (UTC): yesterday", 1
    )

    errors = validator.validate_report_text(report)

    assert any("utc" in error.lower() and "capture" in error.lower() for error in errors)


def test_entries_require_release_context_and_a_source_link() -> None:
    report = make_report().replace("Environment: Development", "Environment: ", 1)
    report = report.replace(
        "Source: [evidence source](https://example.invalid/evidence)",
        "Source: unavailable",
        1,
    )

    errors = validator.validate_report_text(report)

    assert any("environment" in error.lower() for error in errors)
    assert any("source" in error.lower() and "link" in error.lower() for error in errors)


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "123456789012",
        "10.23.4.5",
        "192.168.12.4",
        "Bearer abcdefghijklmnopqrstuvwxyz123456",
        "AKIAABCDEFGHIJKLMNOP",
        "ghp_abcdefghijklmnopqrstuvwxyz1234567890AB",
        "DATASET_MARKER_PRIVATE",
        "customer_id: cust-123",
    ],
)
def test_report_rejects_sensitive_values(sensitive_value: str) -> None:
    report = make_report().replace("evidence source", sensitive_value, 1)

    errors = validator.validate_report_text(report)

    assert any("sensitive" in error.lower() for error in errors)
