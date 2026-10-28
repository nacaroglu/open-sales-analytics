#!/usr/bin/env python3
"""Approval-gated CloudFormation teardown for the temporary Phase 4 stacks.

The default invocation is a local dry run and does not contact AWS. Execute mode
requires an exact confirmation, an expected account, and a configured region.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

STACK_ORDER = ("osa-dev", "osa-prod", "osa-observability", "osa-foundation")
CONFIRMATION = "DELETE-PHASE4-OSA-RESOURCES"
STABLE_STATUSES = frozenset(
    {
        "CREATE_COMPLETE",
        "CREATE_FAILED",
        "DELETE_FAILED",
        "IMPORT_COMPLETE",
        "IMPORT_ROLLBACK_COMPLETE",
        "IMPORT_ROLLBACK_FAILED",
        "ROLLBACK_COMPLETE",
        "ROLLBACK_FAILED",
        "UPDATE_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE",
        "UPDATE_ROLLBACK_FAILED",
    }
)
EXPECTED_ACCOUNT_PATTERN = re.compile(r"^[0-9]{12}$")
MAX_PAGES = 1000


class TeardownError(Exception):
    """A sanitized failure with a safe stage label."""

    def __init__(self, stage: str, *, missing_stack: bool = False) -> None:
        super().__init__(stage)
        self.stage = stage
        self.missing_stack = missing_stack


class AwsClient(Protocol):
    def call(self, *arguments: str) -> dict[str, object]: ...


class AwsCli:
    """Run AWS CLI commands while suppressing identifiers and raw responses."""

    def __init__(self, region: str) -> None:
        self.region = region

    def call(self, *arguments: str) -> dict[str, object]:
        result = subprocess.run(
            ["aws", *arguments, "--region", self.region, "--output", "json"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if (
                len(arguments) >= 2
                and arguments[0:2] == ("cloudformation", "describe-stacks")
                and "does not exist" in result.stderr.lower()
            ):
                raise TeardownError("stack_absent", missing_stack=True)
            raise TeardownError("aws_query")
        try:
            response = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise TeardownError("aws_response") from exc
        if not isinstance(response, dict):
            raise TeardownError("aws_response")
        return response


@dataclass(frozen=True)
class Preflight:
    account_verified: bool
    stack_statuses: dict[str, str | None]


def _pages(client: AwsClient, operation: str, *arguments: str) -> list[dict[str, object]]:
    token: str | None = None
    seen: set[str] = set()
    pages: list[dict[str, object]] = []
    while True:
        command = [operation, *arguments]
        if token is not None:
            command.extend(("--next-token", token))
        response = client.call(*command)
        pages.append(response)
        next_token = response.get("NextToken")
        if next_token is None:
            return pages
        if not isinstance(next_token, str) or not next_token or next_token in seen:
            raise TeardownError("aws_pagination")
        if len(pages) >= MAX_PAGES:
            raise TeardownError("aws_pagination")
        seen.add(next_token)
        token = next_token


def _all_exports(client: AwsClient) -> list[dict[str, object]]:
    exports: list[dict[str, object]] = []
    for page in _pages(client, "cloudformation", "list-exports"):
        entries = page.get("Exports")
        if not isinstance(entries, list):
            raise TeardownError("export_query")
        for entry in entries:
            if not isinstance(entry, dict):
                raise TeardownError("export_query")
            name, exporter = entry.get("Name"), entry.get("ExportingStackId")
            if not isinstance(name, str) or not name or not isinstance(exporter, str):
                raise TeardownError("export_query")
            if _stack_name_from_arn(exporter) is None:
                raise TeardownError("export_query")
            exports.append(entry)
    return exports


def _stack_name_from_arn(stack_id: str) -> str | None:
    match = re.search(r":stack/([^/]+)/[^/]+$", stack_id)
    return match.group(1) if match else None


def _stack_status(client: AwsClient, stack_name: str) -> str | None:
    try:
        response = client.call("cloudformation", "describe-stacks", "--stack-name", stack_name)
    except TeardownError as exc:
        if exc.missing_stack:
            return None
        raise TeardownError("stack_query") from exc
    stacks = response.get("Stacks")
    if not isinstance(stacks, list) or len(stacks) != 1 or not isinstance(stacks[0], dict):
        raise TeardownError("stack_query")
    status = stacks[0].get("StackStatus")
    if not isinstance(status, str):
        raise TeardownError("stack_query")
    if status not in STABLE_STATUSES:
        raise TeardownError("stack_state")
    return status


def preflight(client: AwsClient, expected_account: str) -> Preflight:
    if not EXPECTED_ACCOUNT_PATTERN.fullmatch(expected_account):
        raise TeardownError("account_configuration")
    try:
        identity = client.call("sts", "get-caller-identity")
    except TeardownError as exc:
        raise TeardownError("aws_identity") from exc
    account = identity.get("Account")
    if not isinstance(account, str) or not EXPECTED_ACCOUNT_PATTERN.fullmatch(account):
        raise TeardownError("aws_identity")
    if account != expected_account:
        raise TeardownError("aws_identity")

    statuses = {name: _stack_status(client, name) for name in STACK_ORDER}
    exports = _all_exports(client)
    in_scope = set(STACK_ORDER)
    for entry in exports:
        exporter = _stack_name_from_arn(str(entry["ExportingStackId"]))
        if exporter not in in_scope:
            continue
        export_name = entry["Name"]
        assert isinstance(export_name, str)
        for page in _pages(client, "cloudformation", "list-imports", "--export-name", export_name):
            importers = page.get("Imports")
            if not isinstance(importers, list) or any(
                not isinstance(value, str) for value in importers
            ):
                raise TeardownError("import_query")
            if any(importer not in in_scope for importer in importers):
                raise TeardownError("outside_importer")
    return Preflight(account_verified=True, stack_statuses=statuses)


def teardown(
    client: AwsClient | None,
    expected_account: str,
    confirmation: str,
    *,
    dry_run: bool,
    emit: Callable[[str], None] = print,
) -> int:
    if dry_run:
        emit("Dry run: no AWS calls and no delete operations will be made.")
        emit("Target stacks in deletion order:")
        for index, name in enumerate(STACK_ORDER, start=1):
            emit(f"{index}. {name}")
        return 0
    if client is None:
        raise TeardownError("aws_client")
    if confirmation != CONFIRMATION:
        raise TeardownError("confirmation")

    result = preflight(client, expected_account)
    emit("Preflight passed: account, region, stack states, and export dependencies verified.")
    for name in STACK_ORDER:
        status = result.stack_statuses[name]
        if status is None:
            emit(f"{name}: already absent")
            continue
        emit(f"{name}: deletion started")
        try:
            client.call("cloudformation", "delete-stack", "--stack-name", name)
        except TeardownError as exc:
            emit(
                f"Deletion stopped at {name} (stage: delete_request). Later stacks were not touched."
            )
            raise TeardownError("delete_request") from exc
        try:
            client.call("cloudformation", "wait", "stack-delete-complete", "--stack-name", name)
        except TeardownError as exc:
            emit(f"Deletion stopped at {name} (stage: delete_wait). Later stacks were not touched.")
            raise TeardownError("delete_wait") from exc
        emit(f"{name}: deleted")
    emit("Teardown completed for the configured Phase 4 stacks.")
    return 0


def _summary_text(lines: list[str], failure_stage: str | None) -> str:
    outcomes = {name: "not attempted" for name in STACK_ORDER}
    active: str | None = None
    for line in lines:
        for name in STACK_ORDER:
            if line == f"{name}: already absent":
                outcomes[name] = "already absent"
            elif line == f"{name}: deletion started":
                outcomes[name] = "deletion started"
                active = name
            elif line == f"{name}: deleted":
                outcomes[name] = "deleted"
                active = None
        if line.startswith("Deletion stopped at "):
            parts = line.split()
            if len(parts) > 3 and parts[3] in outcomes:
                active = parts[3]
                outcomes[active] = "failed"

    if active is not None and outcomes[active] == "deletion started":
        outcomes[active] = "failed"
    successful = any(
        marker in line
        for marker in ("Dry run:", "Preflight passed", "Teardown completed")
        for line in lines
    )
    stage = failure_stage or ("none" if successful else "unknown")
    table = ["| Stack | Outcome |", "| --- | --- |"]
    table.extend(f"| `{name}` | {outcomes[name]} |" for name in STACK_ORDER)
    return "\n".join(
        ["## Phase 4 teardown result", "", f"Safe failure stage: `{stage}`", "", *table, ""]
    )


def _write_step_summary(path: str | None, lines: list[str], failure_stage: str | None) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as summary:
        summary.write(_summary_text(lines, failure_stage))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="print the exact stack order without AWS calls"
    )
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="verify account, stacks, and imports without deleting",
    )
    mode.add_argument(
        "--execute", action="store_true", help="preflight and delete the configured stacks"
    )
    parser.add_argument("--confirm", default="", help="exact execution confirmation value")
    args = parser.parse_args(argv)

    output: list[str] = []

    def emit(line: str) -> None:
        output.append(line)
        print(line)

    if not args.execute and not args.preflight_only:
        result = teardown(None, "", args.confirm, dry_run=True, emit=emit)
        _write_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), output, None)
        return result

    region = os.environ.get("OSA_AWS_REGION", "")
    expected_account = os.environ.get("OSA_TEARDOWN_AWS_ACCOUNT_ID", "")
    if not region or region != os.environ.get("AWS_REGION", region):
        emit("Teardown stopped (stage: region_configuration).")
        _write_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), output, "region_configuration")
        return 2
    if args.execute and args.confirm != CONFIRMATION:
        emit("Teardown stopped (stage: confirmation).")
        _write_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), output, "confirmation")
        return 2
    try:
        client = AwsCli(region)
        if args.preflight_only:
            preflight(client, expected_account)
            emit(
                "Preflight passed: account, region, stack states, and export dependencies verified."
            )
            _write_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), output, None)
            return 0
        result = teardown(
            client,
            expected_account,
            args.confirm,
            dry_run=False,
            emit=emit,
        )
        _write_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), output, None)
        return result
    except TeardownError as exc:
        emit(f"Teardown stopped (stage: {exc.stage}).")
        _write_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), output, exc.stage)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
