from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.verify_phase4_resource_absence import (
    RESOURCE_CATEGORIES,
    STACKS,
    VerificationError,
    _pages,
    discover,
    main,
    verify,
)


class FakeAws:
    def __init__(self, *, remaining: bool = False, fail: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.remaining = remaining
        self.fail = fail

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        service, operation = command[1:3]
        if self.fail == operation:
            return subprocess.CompletedProcess(command, 254, "", "AccessDeniedException: private")
        if service == "cloudformation":
            return subprocess.CompletedProcess(command, 0, '{"Stacks": []}', "")
        key_by_operation = {
            ("ec2", "describe-instances"): "Reservations",
            ("ec2", "describe-volumes"): "Volumes",
            ("ec2", "describe-addresses"): "Addresses",
            ("ec2", "describe-snapshots"): "Snapshots",
            ("ssm", "describe-parameters"): "Parameters",
            ("iam", "list-roles"): "Roles",
            ("ecr", "describe-repositories"): "repositories",
        }
        key = key_by_operation.get((service, operation))
        if key:
            values: list[dict] = []
            if self.remaining and service == "ec2" and operation == "describe-instances":
                values = [
                    {
                        "Instances": [
                            {
                                "Tags": [
                                    {"Key": "Project", "Value": "open-sales-analytics"},
                                    {"Key": "OSAStack", "Value": "osa-dev"},
                                ]
                            }
                        ]
                    }
                ]
            payload = {key: values}
            if key == "Roles":
                payload["IsTruncated"] = False
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        if service == "ssm":
            return subprocess.CompletedProcess(command, 0, '{"TagList": []}', "")
        if service == "ecr":
            return subprocess.CompletedProcess(command, 0, '{"tags": []}', "")
        raise AssertionError(f"Unexpected AWS operation: {service} {operation}")


def test_complete_absence_report_checks_all_categories_and_never_mutates() -> None:
    aws = FakeAws()
    result = verify("us-east-1", runner=aws, timeout_seconds=1, poll_seconds=0.1)
    assert result["result"] == "PASS"
    assert result["verified_at_utc"].endswith("+00:00")
    assert result["region"] == "us-east-1"
    assert result["target_stacks"] == list(STACKS)
    assert result["checked_stacks"] == [
        "osa-dev",
        "osa-prod",
        "osa-observability",
        "osa-foundation",
    ]
    assert set(result["categories"]) == {
        "CloudFormation stacks",
        "EC2 instances",
        "EBS volumes",
        "Elastic IPs",
        "EBS snapshots",
        "SSM parameters",
        "OSA IAM roles",
        "ECR repositories and images",
        "Route 53 records",
    }
    assert all(count == 0 for count in result["categories"].values())
    assert not any(
        operation
        in {
            "delete-stack",
            "delete-repository",
            "delete-volume",
            "release-address",
            "delete-parameter",
            "delete-role",
            "delete-record-set",
        }
        for call in aws.calls
        for operation in call
    )


def test_access_denied_fails_closed_without_echoing_raw_error() -> None:
    with pytest.raises(VerificationError) as error:
        discover(FakeAws(fail="describe-volumes"), "us-east-1", "open-sales-analytics")
    assert "AccessDeniedException" not in str(error.value)
    assert "private" not in str(error.value)

    with pytest.raises(VerificationError) as verification_error:
        verify(
            "us-east-1",
            runner=FakeAws(fail="describe-volumes"),
            timeout_seconds=1,
            poll_seconds=0.1,
        )
    assert verification_error.value.checked_categories == (
        "CloudFormation stacks",
        "EC2 instances",
    )
    assert verification_error.value.checked_stacks == STACKS


def test_query_failure_report_names_checked_stacks_and_categories(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_query(*_: object, **__: object) -> dict[str, object]:
        raise VerificationError(
            "AWS query failed.",
            checked_stacks=("osa-dev",),
            checked_categories=("CloudFormation stacks",),
        )

    monkeypatch.setattr("scripts.verify_phase4_resource_absence.verify", fail_query)
    assert main(["--region", "us-east-1"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["result"] == "FAIL"
    assert report["target_stacks"] == list(STACKS)
    assert report["checked_stacks"] == ["osa-dev"]
    assert report["checked_categories"] == ["CloudFormation stacks"]


def test_preflight_failure_report_has_empty_checked_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--region", "not-a-region"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["result"] == "FAIL"
    assert report["target_stacks"] == list(STACKS)
    assert report["checked_stacks"] == []
    assert report["checked_categories"] == []


def test_cloudformation_failure_reports_only_stacks_queried_so_far() -> None:
    aws = FakeAws()

    def fail_on_second_stack(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["cloudformation", "describe-stacks"] and command[4] == "osa-prod":
            aws.calls.append(command)
            return subprocess.CompletedProcess(command, 254, "", "AccessDeniedException: private")
        return aws(command, **kwargs)

    with pytest.raises(VerificationError) as error:
        verify("us-east-1", runner=fail_on_second_stack, timeout_seconds=1, poll_seconds=0.1)

    assert error.value.checked_stacks == ("osa-dev",)
    assert error.value.checked_categories == ()


def test_owned_resource_is_reported_by_category_without_its_id() -> None:
    aws = FakeAws(remaining=True)
    with pytest.raises(VerificationError) as error:
        verify(
            "us-east-1",
            runner=aws,
            timeout_seconds=0.01,
            poll_seconds=0.01,
            monotonic=iter([0.0, 2.0]).__next__,
        )
    assert "EC2 instances" in str(error.value)
    assert "i-" not in str(error.value)
    assert error.value.checked_categories == RESOURCE_CATEGORIES


def test_eventual_absence_is_rechecked_with_bounded_polling() -> None:
    aws = FakeAws(remaining=True)
    slept = 0.0

    def sleep(seconds: float) -> None:
        nonlocal slept
        slept += seconds
        aws.remaining = False

    result = verify(
        "us-east-1",
        runner=aws,
        timeout_seconds=1,
        poll_seconds=0.25,
        monotonic=lambda: slept,
        sleep=sleep,
    )
    assert result["result"] == "PASS"
    assert slept == 0.25


def test_pagination_follows_every_token_and_detects_cycles() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        token = "--starting-token" in command
        payload = (
            {"Items": [{"name": "second"}], "NextToken": "page-2"}
            if not token
            else {
                "Items": [{"name": "third"}],
            }
        )
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    assert _pages(runner, ["ec2", "describe-volumes"], "Items", region="us-east-1") == [
        {"name": "second"},
        {"name": "third"},
    ]
    assert len(calls) == 2
    assert "page-2" in calls[1]

    def iam_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if "--starting-token" in command:
            payload = {"Roles": [{"RoleName": "last"}], "IsTruncated": False}
        else:
            payload = {"Roles": [{"RoleName": "first"}], "IsTruncated": True, "Marker": "next"}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    assert [
        role["RoleName"]
        for role in _pages(iam_runner, ["iam", "list-roles"], "Roles", region="us-east-1")
    ] == ["first", "last"]


def test_malformed_query_and_invalid_region_fail_closed() -> None:
    def malformed(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, '{"Volumes": null}', "")

    with pytest.raises(VerificationError, match="incomplete resource listing"):
        _pages(malformed, ["ec2", "describe-volumes"], "Volumes", region="us-east-1")
    with pytest.raises(VerificationError, match="region"):
        verify("not-a-region", runner=FakeAws())


def test_external_similarly_named_or_tagged_resources_are_not_in_scope() -> None:
    assert not __import__("scripts.verify_phase4_resource_absence", fromlist=["_owned"])._owned(
        [
            {"Key": "Project", "Value": "open-sales-analytics"},
            {"Key": "OSAStack", "Value": "external-stack"},
        ],
        "osa-foundation",
    )
