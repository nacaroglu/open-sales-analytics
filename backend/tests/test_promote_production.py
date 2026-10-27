import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "promote_production.py"
SPEC = importlib.util.spec_from_file_location("promote_production", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROMOTION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROMOTION
SPEC.loader.exec_module(PROMOTION)

REGION = "eu-central-1"
REPOSITORY = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/open-sales-analytics"
DEV_ROLE = "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-production-source-read"
PROD_ROLE = "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-prod-promotion"
EXEC_ROLE = (
    "arn:aws:iam::123456789012:role/osa-foundation/osa-foundation-osa-prod-application-execution"
)
DIGEST = "a" * 64
OLD_DIGEST = "b" * 64
VERSION = "20261027-133045-abcdef0"
OLD_VERSION = "20261026-133045-abcdef0"


def config(**overrides: str):
    values = {
        "region": REGION,
        "repository": REPOSITORY,
        "source_read_role": DEV_ROLE,
        "promotion_role": PROD_ROLE,
        "execution_role": EXEC_ROLE,
        "ami": "ami-0123456789abcdef0",
        "instance_type": "t3.small",
        "hostname": "sales.example.com",
    }
    values.update(overrides)
    return PROMOTION.Config(**values)


def describe_json(stack: str, digest: str, version: str) -> str:
    return json.dumps(
        {
            "Stacks": [
                {
                    "StackName": stack,
                    "StackStatus": "UPDATE_COMPLETE",
                    "Outputs": [
                        {
                            "OutputKey": "ImageReference",
                            "OutputValue": f"{REPOSITORY}@sha256:{digest}",
                        },
                        {"OutputKey": "ReleaseVersion", "OutputValue": version},
                    ],
                }
            ]
        }
    )


def test_dev_metadata_is_parsed_and_bound_to_expected_ecr_repository():
    release = PROMOTION.parse_release(
        describe_json("osa-dev", DIGEST, VERSION), "osa-dev", REPOSITORY
    )

    assert release == PROMOTION.Release(DIGEST, VERSION)


@pytest.mark.parametrize(
    ("payload", "repository"),
    [
        ("{}", REPOSITORY),
        (describe_json("osa-prod", DIGEST, VERSION), REPOSITORY),
        (describe_json("osa-dev", "short", VERSION), REPOSITORY),
        (describe_json("osa-dev", DIGEST, "latest"), REPOSITORY),
        (
            describe_json("osa-dev", DIGEST, VERSION),
            "123456789012.dkr.ecr.eu-central-1.amazonaws.com/other",
        ),
        (
            json.dumps(
                {
                    "Stacks": [
                        {"StackName": "osa-dev", "StackStatus": "UPDATE_IN_PROGRESS", "Outputs": []}
                    ]
                }
            ),
            REPOSITORY,
        ),
    ],
)
def test_missing_or_malformed_dev_metadata_is_rejected(payload: str, repository: str):
    with pytest.raises(PROMOTION.PromotionError):
        PROMOTION.parse_release(payload, "osa-dev", repository)


def test_promotion_uses_only_the_dev_digest_and_never_builds_pushes_or_retags(tmp_path: Path):
    commands: list[list[str]] = []

    def runner(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        args = list(command)
        commands.append(args)
        if args[:3] == ["aws", "cloudformation", "describe-stacks"]:
            return subprocess.CompletedProcess(
                args, 0, stdout=describe_json("osa-prod", OLD_DIGEST, OLD_VERSION)
            )
        return subprocess.CompletedProcess(args, 0, stdout="")

    summary = tmp_path / "summary.md"
    source = PROMOTION.Release(DIGEST, VERSION)
    previous = PROMOTION.promote(
        config(), source, runner=runner, env={"GITHUB_STEP_SUMMARY": str(summary)}
    )

    assert previous == PROMOTION.Release(OLD_DIGEST, OLD_VERSION)
    update = next(
        command for command in commands if command[:3] == ["aws", "cloudformation", "update-stack"]
    )
    assert update[update.index("--stack-name") + 1] == "osa-prod"
    assert f"ParameterKey=ImageDigest,ParameterValue={DIGEST}" in update
    assert f"ParameterKey=ReleaseVersion,ParameterValue={VERSION}" in update
    assert not any(
        any(
            word in " ".join(command).lower()
            for word in ("docker", "build", "push", "retag", "aws ecr")
        )
        for command in commands
    )
    assert "osa-prod update wait" not in summary.read_text(encoding="utf-8")
    contents = summary.read_text(encoding="utf-8")
    assert (
        DIGEST in contents
        and VERSION in contents
        and OLD_DIGEST in contents
        and OLD_VERSION in contents
    )


def test_invalid_source_release_fails_before_any_aws_command():
    def unexpected_runner(*_: object, **__: object):
        pytest.fail("AWS must not be called for malformed metadata")

    with pytest.raises(PROMOTION.PromotionError):
        PROMOTION.promote(
            config(), PROMOTION.Release("bad", "latest"), runner=unexpected_runner, env={}
        )


@pytest.mark.parametrize(
    "override",
    [
        {"source_read_role": ""},
        {"repository": "example.invalid/image"},
        {"promotion_role": "arn:aws:iam::123456789012:role/other"},
    ],
)
def test_invalid_static_configuration_is_rejected(override: dict[str, str]):
    with pytest.raises(PROMOTION.PromotionError):
        PROMOTION.validate_config(config(**override))
