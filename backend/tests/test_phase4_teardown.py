from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import teardown_phase4 as phase4_teardown
import verify_phase4_environment as environment_verifier
from teardown_phase4 import CONFIRMATION, STACK_ORDER, TeardownError, teardown


def _arn(stack: str) -> str:
    return f"arn:aws:cloudformation:eu-central-1:123456789012:stack/{stack}/id"


class FakeAws:
    def __init__(
        self,
        *,
        imports: list[str] | None = None,
        fail: str | None = None,
        absent: tuple[str, ...] = (),
        paginated_imports: bool = False,
        paginated_exports: bool = False,
    ) -> None:
        self.imports = imports or []
        self.fail = fail
        self.absent = absent
        self.paginated_imports = paginated_imports
        self.paginated_exports = paginated_exports
        self.calls: list[tuple[str, ...]] = []

    def call(self, *arguments: str) -> dict[str, object]:
        self.calls.append(arguments)
        if arguments[:2] == ("sts", "get-caller-identity"):
            return {"Account": "123456789012"}
        if arguments[:2] == ("cloudformation", "describe-stacks"):
            if arguments[-1] in self.absent:
                raise TeardownError("stack_absent", missing_stack=True)
            return {"Stacks": [{"StackStatus": "CREATE_COMPLETE"}]}
        if arguments[:2] == ("cloudformation", "list-exports"):
            if self.paginated_exports:
                if "--next-token" not in arguments:
                    return {
                        "Exports": [
                            {"Name": "foundation-vpc", "ExportingStackId": _arn("osa-foundation")}
                        ],
                        "NextToken": "exports-page",
                    }
                assert arguments[arguments.index("--next-token") + 1] == "exports-page"
                return {
                    "Exports": [
                        {"Name": "collector-sg", "ExportingStackId": _arn("osa-observability")}
                    ]
                }
            return {
                "Exports": [
                    {"Name": "foundation-vpc", "ExportingStackId": _arn("osa-foundation")},
                    {"Name": "collector-sg", "ExportingStackId": _arn("osa-observability")},
                    {"Name": "outside", "ExportingStackId": _arn("unrelated")},
                ]
            }
        if arguments[:2] == ("cloudformation", "list-imports"):
            name = arguments[arguments.index("--export-name") + 1]
            if name == "foundation-vpc":
                return {"Imports": ["osa-dev", "osa-prod", "osa-observability"]}
            if name == "collector-sg":
                if self.paginated_imports:
                    if "--next-token" not in arguments:
                        return {"Imports": ["osa-dev"], "NextToken": "next-page"}
                    assert arguments[arguments.index("--next-token") + 1] == "next-page"
                    return {"Imports": ["osa-prod"]}
                return {"Imports": [*self.imports]}
            return {"Imports": ["unrelated"]}
        if arguments[:2] == ("cloudformation", "delete-stack"):
            if self.fail == "delete":
                raise TeardownError("aws_query")
            return {}
        if arguments[:2] == ("cloudformation", "wait"):
            if self.fail == "wait":
                raise TeardownError("aws_query")
            return {}
        raise AssertionError(arguments)


def test_dry_run_reports_exact_order_without_aws_calls() -> None:
    client = FakeAws()
    output: list[str] = []

    assert teardown(client, "", "", dry_run=True, emit=output.append) == 0
    assert client.calls == []
    assert output[0].startswith("Dry run:")
    assert output[1:] == ["Target stacks in deletion order:"] + [
        f"{index}. {name}" for index, name in enumerate(STACK_ORDER, 1)
    ]


def test_exact_confirmation_is_required_before_any_aws_call() -> None:
    client = FakeAws()

    with pytest.raises(TeardownError, match="confirmation"):
        teardown(client, "123456789012", "DELETE", dry_run=False)
    assert client.calls == []


def test_preflight_allows_only_known_in_scope_importers_and_deletes_in_order() -> None:
    client = FakeAws(imports=["osa-dev", "osa-prod"])
    output: list[str] = []

    assert teardown(client, "123456789012", CONFIRMATION, dry_run=False, emit=output.append) == 0
    delete_calls = [
        call[-1] for call in client.calls if call[:2] == ("cloudformation", "delete-stack")
    ]
    wait_calls = [call[-1] for call in client.calls if call[:2] == ("cloudformation", "wait")]
    assert delete_calls == list(STACK_ORDER)
    assert wait_calls == list(STACK_ORDER)
    for name in STACK_ORDER:
        delete_index = client.calls.index(("cloudformation", "delete-stack", "--stack-name", name))
        wait_index = client.calls.index(
            ("cloudformation", "wait", "stack-delete-complete", "--stack-name", name)
        )
        if name != STACK_ORDER[-1]:
            next_delete = client.calls.index(
                (
                    "cloudformation",
                    "delete-stack",
                    "--stack-name",
                    STACK_ORDER[STACK_ORDER.index(name) + 1],
                )
            )
            assert delete_index < wait_index < next_delete
    assert output[-1] == "Teardown completed for the configured Phase 4 stacks."
    assert "123456789012" not in "\n".join(output)


def test_preflight_refuses_outside_export_importers_before_delete() -> None:
    client = FakeAws(imports=["customer-stack"])

    with pytest.raises(TeardownError, match="outside_importer"):
        teardown(client, "123456789012", CONFIRMATION, dry_run=False)
    assert not any(call[:2] == ("cloudformation", "delete-stack") for call in client.calls)


def test_importer_listing_follows_all_pages_before_delete() -> None:
    client = FakeAws(paginated_imports=True)

    assert (
        teardown(client, "123456789012", CONFIRMATION, dry_run=False, emit=lambda _line: None) == 0
    )
    assert any(
        "--next-token" in call and call[call.index("--next-token") + 1] == "next-page"
        for call in client.calls
    )


def test_export_listing_follows_all_pages() -> None:
    client = FakeAws(imports=["osa-dev"], paginated_exports=True)

    assert (
        teardown(client, "123456789012", CONFIRMATION, dry_run=False, emit=lambda _line: None) == 0
    )
    assert any(
        call[:2] == ("cloudformation", "list-exports")
        and "--next-token" in call
        and call[call.index("--next-token") + 1] == "exports-page"
        for call in client.calls
    )


def test_missing_stack_is_reported_and_skipped_safely() -> None:
    client = FakeAws(absent=("osa-prod",))
    output: list[str] = []

    assert teardown(client, "123456789012", CONFIRMATION, dry_run=False, emit=output.append) == 0
    delete_names = [
        call[-1] for call in client.calls if call[:2] == ("cloudformation", "delete-stack")
    ]
    assert delete_names == ["osa-dev", "osa-observability", "osa-foundation"]
    assert "osa-prod: already absent" in output


@pytest.mark.parametrize("failure", ["delete", "wait"])
def test_deletion_failure_stops_before_later_stacks(failure: str) -> None:
    client = FakeAws(fail=failure)
    output: list[str] = []

    with pytest.raises(TeardownError):
        teardown(client, "123456789012", CONFIRMATION, dry_run=False, emit=output.append)
    delete_names = [
        call[-1] for call in client.calls if call[:2] == ("cloudformation", "delete-stack")
    ]
    assert delete_names == [STACK_ORDER[0]]
    assert "Later stacks were not touched." in output[-1]


def test_wrong_aws_account_refuses_before_stack_queries() -> None:
    class WrongAccount(FakeAws):
        def call(self, *arguments: str) -> dict[str, object]:
            self.calls.append(arguments)
            return {"Account": "999999999999"}

    client = WrongAccount()

    with pytest.raises(TeardownError, match="aws_identity"):
        teardown(client, "123456789012", CONFIRMATION, dry_run=False)
    assert client.calls == [("sts", "get-caller-identity")]


def test_cli_defaults_to_local_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry run must not create an AWS client")

    monkeypatch.setattr(phase4_teardown, "AwsCli", fail_if_called)
    assert phase4_teardown.main([]) == 0
    output = capsys.readouterr().out
    assert "1. osa-dev" in output
    assert "4. osa-foundation" in output


def test_cli_preflight_only_never_deletes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeAws(imports=["osa-dev"])
    monkeypatch.setenv("OSA_AWS_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("OSA_TEARDOWN_AWS_ACCOUNT_ID", "123456789012")
    monkeypatch.setattr(phase4_teardown, "AwsCli", lambda _region: client)

    assert phase4_teardown.main(["--preflight-only"]) == 0
    assert "Preflight passed" in capsys.readouterr().out
    assert not any(call[:2] == ("cloudformation", "delete-stack") for call in client.calls)


def test_execution_failure_writes_safe_per_stack_step_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    summary_path = tmp_path / "summary.md"
    client = FakeAws(fail="delete")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("OSA_AWS_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("OSA_TEARDOWN_AWS_ACCOUNT_ID", "123456789012")
    monkeypatch.setattr(phase4_teardown, "AwsCli", lambda _region: client)

    assert phase4_teardown.main(["--execute", "--confirm", CONFIRMATION]) == 2
    capsys.readouterr()
    summary = summary_path.read_text(encoding="utf-8")
    assert "Safe failure stage: `delete_request`" in summary
    assert "| `osa-dev` | failed |" in summary
    assert "| `osa-prod` | not attempted |" in summary
    assert "123456789012" not in summary


def test_environment_verifier_requires_a_nonempty_required_reviewers_rule() -> None:
    environment_verifier.validate_environment_protection(
        {
            "protection_rules": [
                {"type": "required_reviewers", "reviewers": [{"type": "User", "id": 17}]}
            ]
        }
    )

    with pytest.raises(ValueError, match="no required reviewers"):
        environment_verifier.validate_environment_protection(
            {"protection_rules": [{"type": "required_reviewers", "reviewers": []}]}
        )


def test_environment_verifier_rejects_missing_protection_rules() -> None:
    with pytest.raises(ValueError, match="protection rules are missing"):
        environment_verifier.validate_environment_protection({})
