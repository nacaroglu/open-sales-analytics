import importlib.util
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

PUBLISHER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "publish_ecr_image.py"
PUBLISHER_SPEC = importlib.util.spec_from_file_location("publish_ecr_image", PUBLISHER_PATH)
assert PUBLISHER_SPEC is not None and PUBLISHER_SPEC.loader is not None
PUBLISHER = importlib.util.module_from_spec(PUBLISHER_SPEC)
PUBLISHER_SPEC.loader.exec_module(PUBLISHER)
PublishError = PUBLISHER.PublishError
publish_image = PUBLISHER.publish_image

REPOSITORY_URI = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/osa"
VERSION = "20261027-133045-abcdef0"
DIGEST = "sha256:" + "a" * 64


def runner_for(
    *,
    digest: str = DIGEST,
    fail_command: str | None = None,
) -> tuple[object, list[tuple[list[str], str | None]]]:
    calls: list[tuple[list[str], str | None]] = []

    def run(
        command: Sequence[str],
        *,
        input: str | None = None,
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        args = list(command)
        calls.append((args, input))
        command_name = " ".join(args[:3] if args[:2] == ["aws", "ecr"] else args[:2])
        if fail_command == command_name:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="credential-marker")
        if args[:4] == ["aws", "ecr", "get-login-password", "--region"]:
            return subprocess.CompletedProcess(args, 0, stdout="temporary-token-marker", stderr="")
        if args[:3] == ["aws", "ecr", "describe-images"]:
            return subprocess.CompletedProcess(args, 0, stdout=digest, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    return run, calls


def test_publish_pushes_existing_image_tag_once_and_exports_digest(tmp_path: Path) -> None:
    runner, calls = runner_for()
    output_path = tmp_path / "github-output"

    outputs = publish_image(
        repository_uri=REPOSITORY_URI,
        version=VERSION,
        region="eu-central-1",
        output_path=output_path,
        runner=runner,
    )

    assert calls[0][0] == ["aws", "ecr", "get-login-password", "--region", "eu-central-1"]
    assert calls[1][0] == [
        "docker",
        "login",
        "--username",
        "AWS",
        "--password-stdin",
        "123456789012.dkr.ecr.eu-central-1.amazonaws.com",
    ]
    assert calls[1][1] == "temporary-token-marker"
    assert calls[2][0] == ["docker", "tag", "open-sales-analytics", f"{REPOSITORY_URI}:{VERSION}"]
    assert calls[3][0] == ["docker", "push", f"{REPOSITORY_URI}:{VERSION}"]
    assert calls[4][0][0:3] == ["aws", "ecr", "describe-images"]
    assert calls[4][0][-3:] == ["imageDetails[0].imageDigest", "--output", "text"]
    assert outputs == {
        "repository-uri": REPOSITORY_URI,
        "release-version": VERSION,
        "digest": DIGEST,
        "image-ref": f"{REPOSITORY_URI}@{DIGEST}",
    }
    assert output_path.read_text(encoding="utf-8") == (
        f"repository-uri={REPOSITORY_URI}\nrelease-version={VERSION}\n"
        f"digest={DIGEST}\nimage-ref={REPOSITORY_URI}@{DIGEST}\n"
    )


@pytest.mark.parametrize(
    ("digest", "fail_command", "message"),
    [
        ("", None, "missing or malformed"),
        ("sha256:ABC", None, "missing or malformed"),
        (DIGEST, "docker push", "ECR image push failed"),
        (DIGEST, "aws ecr get-login-password", "ECR authentication token request failed"),
        (DIGEST, "aws ecr describe-images", "ECR digest lookup failed"),
    ],
)
def test_publish_failures_are_clear_and_do_not_expose_command_output(
    tmp_path: Path,
    digest: str,
    fail_command: str | None,
    message: str,
) -> None:
    runner, _ = runner_for(digest=digest, fail_command=fail_command)
    output_path = tmp_path / "github-output"

    with pytest.raises(PublishError, match=message) as error:
        publish_image(
            repository_uri=REPOSITORY_URI,
            version=VERSION,
            region="eu-central-1",
            output_path=output_path,
            runner=runner,
        )

    assert "credential-marker" not in str(error.value)
    if fail_command == "docker push":
        assert "immutable tag collisions are not overwritten" in str(error.value)
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("repository_uri", "version", "region"),
    [
        ("", VERSION, "eu-central-1"),
        (REPOSITORY_URI, "mutable-tag", "eu-central-1"),
        (REPOSITORY_URI, VERSION, ""),
    ],
)
def test_publish_rejects_malformed_configuration_before_commands(
    tmp_path: Path,
    repository_uri: str,
    version: str,
    region: str,
) -> None:
    runner, calls = runner_for()

    with pytest.raises(PublishError):
        publish_image(
