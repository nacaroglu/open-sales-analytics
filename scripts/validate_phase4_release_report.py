#!/usr/bin/env python3
"""Validate the offline Phase 4 release evidence report without live services."""

from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path

REPORT_PATH = Path(__file__).resolve().parents[1] / "_docs" / "phase-4-release-report.md"

ENTRY_LABELS = (
    "Successful PR CI jobs",
    "Immutable ECR tag and image digest",
    "Development deployment readiness and smoke results",
    "Production promotion using the same digest",
    "Development and production application pages",
    "Grafana views filtered by environment and version",
    "Trace connected to correlated logs",
    "Controlled failures and firing/resolved alert",
    "Rollback demonstration or automated rollback test",
    "CloudFormation stack and resource summary",
    "Final cleanup commands and deletion verification",
)

_SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FIELD_NAMES = (
    "Evidence status",
    "Source",
    "Evidence captured at (UTC)",
    "Status checked at (UTC)",
    "Environment",
    "Release/version",
    "Evidence type",
)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\bAWS_SECRET_ACCESS_KEY\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\b(?:DATASET|ORDER|PRODUCT|CUSTOMER)_MARKER_[A-Za-z0-9_-]+\b", re.IGNORECASE),
    re.compile(
        r"\b(?:dataset|customer|order|product)(?:_id|\s+id)\s*[:=]\s*[A-Za-z0-9_-]{3,}",
        re.IGNORECASE,
    ),
    re.compile(r"(?<![A-Fa-f0-9])\d{12}(?![A-Fa-f0-9])"),
    re.compile(r"https?://[^/\s:@]+:[^/@\s]+@", re.IGNORECASE),
)
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def _is_pending(value: str) -> bool:
    return value.startswith("Pending —") or value.startswith("Pending -")


def _field(section: str, name: str) -> str | None:
    match = re.search(rf"^{re.escape(name)}:[ \t]*(.+?)[ \t]*$", section, re.MULTILINE)
    return match.group(1).strip().strip("`").strip() if match else None


def _has_sensitive_value(text: str) -> bool:
    if any(pattern.search(text) for pattern in _SENSITIVE_VALUE_PATTERNS):
        return True
    for candidate in _IPV4_RE.findall(text):
        try:
            if ipaddress.ip_address(candidate).is_private:
                return True
        except ValueError:
            continue
    return False


def validate_report_text(text: str) -> list[str]:
    """Return safe, actionable validation errors for report text."""
    errors: list[str] = []
    if _has_sensitive_value(text):
        errors.append("Report contains a value matching a prohibited sensitive-data pattern.")

    headings = list(_SECTION_RE.finditer(text))
    if len(headings) != len(ENTRY_LABELS):
        errors.append(
            f"Report must contain exactly 11 labeled evidence entries; found {len(headings)}."
        )

    sections: list[tuple[int, str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append((int(heading.group(1)), heading.group(2), text[heading.end() : end]))

    complete_count = 0
    pending_count = 0
    for expected_number, expected_label in enumerate(ENTRY_LABELS, start=1):
        matches = [entry for entry in sections if entry[0] == expected_number]
        if len(matches) != 1:
            errors.append(
                f"Evidence entry {expected_number} ({expected_label}) is missing or duplicated."
            )
            continue
        number, label, section = matches[0]
        if label != expected_label:
            errors.append(f"Evidence entry {number} has an unexpected label.")
        values = {name: _field(section, name) for name in _FIELD_NAMES}
        for name, value in values.items():
            if not value:
                errors.append(f"Evidence entry {number} is missing {name}.")

        status = values["Evidence status"] or ""
        captured = values["Evidence captured at (UTC)"] or ""
        checked = values["Status checked at (UTC)"] or ""
        evidence_type = values["Evidence type"] or ""
        source = values["Source"] or ""

        links = _MARKDOWN_LINK_RE.findall(source)
        if not links:
            errors.append(f"Evidence entry {number} must link to a source or artifact.")
        elif any(
            not (
                link.startswith("https://")
                or (link.startswith("_docs/") and ".." not in link.split("/"))
            )
            for link in links
        ):
            errors.append(
                f"Evidence entry {number} contains a source link that is not HTTPS or a safe docs path."
            )

        if not _UTC_RE.fullmatch(checked):
            errors.append(f"Evidence entry {number} has an invalid status-check UTC timestamp.")
        if evidence_type not in {"Automated", "Live", "Automated and live"}:
            errors.append(f"Evidence entry {number} must identify evidence as Automated or Live.")

        if status == "Complete":
            complete_count += 1
            if not _UTC_RE.fullmatch(captured):
                errors.append(
                    f"Evidence entry {number} marked complete requires an ISO-8601 UTC capture timestamp."
                )
            if re.search(
                r"^Operator action:\s*(?:Pending|TBD|None)\s*$",
                section,
                re.MULTILINE | re.IGNORECASE,
            ):
                errors.append(
                    f"Evidence entry {number} marked complete has an unresolved operator action."
                )
        elif _is_pending(status):
            pending_count += 1
            reason = status.partition("—")[2] if "—" in status else status.partition("-")[2]
            action = re.search(r"^Operator action:\s*(.+?)\s*$", section, re.MULTILINE)
            if not reason.strip():
                errors.append(f"Evidence entry {number} marked pending must state a reason.")
            if not action or action.group(1).strip().lower() in {"", "pending", "tbd", "none"}:
                errors.append(
                    f"Evidence entry {number} marked pending requires a specific operator action."
                )
            if not _is_pending(captured):
                errors.append(
                    f"Evidence entry {number} marked pending must not claim an evidence capture timestamp."
                )
        else:
            errors.append(
                f"Evidence entry {number} status must be Complete or Pending with a reason."
            )

    overall = re.search(r"^Overall status:\s*(.+?)\s*$", text, re.MULTILINE)
    if not overall:
        errors.append("Report is missing its Overall status.")
    elif pending_count:
        if not overall.group(1).lower().startswith("incomplete"):
            errors.append("Overall status must be Incomplete while any evidence entry is Pending.")
    elif complete_count == len(ENTRY_LABELS) and not overall.group(1).lower().startswith(
        "complete"
    ):
        errors.append("Overall status must be Complete when all evidence entries are Complete.")

    return errors


def main() -> int:
    try:
        text = REPORT_PATH.read_text(encoding="utf-8")
    except OSError:
        print("Phase 4 release report is missing or unreadable.", file=sys.stderr)
        return 1

    errors = validate_report_text(text)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    statuses = [_field(section, "Evidence status") or "" for _, _, section in _split_sections(text)]
    complete = sum(status == "Complete" for status in statuses)
    pending = len(statuses) - complete
    print(f"Validated 11 evidence entries: {complete} complete, {pending} pending.")
    if pending:
        print(
            "Report remains incomplete; pending entries are not treated as demonstration evidence."
        )
    return 0


def _split_sections(text: str) -> list[tuple[int, str, str]]:
    headings = list(_SECTION_RE.finditer(text))
    result = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        result.append((int(heading.group(1)), heading.group(2), text[heading.end() : end]))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
