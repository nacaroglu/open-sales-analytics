import importlib.util
from pathlib import Path

import pytest

VALIDATOR_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_ci_parallelism.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("validate_ci_parallelism", VALIDATOR_PATH)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)


def test_ci_validator_rejects_a_workflow_without_main_push_trigger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    original_trigger = "branches: [main, 'feature/issue-*']"
    assert original_trigger in source
    altered_workflow = tmp_path / "ci.yml"
    altered_workflow.write_text(
        source.replace(original_trigger, "branches: ['feature/issue-*']"), encoding="utf-8"
    )
    monkeypatch.setattr(VALIDATOR, "WORKFLOW", altered_workflow)

    with pytest.raises(SystemExit):
        VALIDATOR.validate()

    assert "push workflow must include main" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main' && needs.publish-ecr.result == 'success'",
            "if: always()",
            "deploy-dev is missing required ordering",
        ),
        (
            "needs.publish-ecr.outputs.image-ref",
            "vars.OSA_ECR_REPOSITORY_URI",
            "deploy-dev is missing required ordering",
        ),
        (
            "role-to-assume: ${{ vars.OSA_DEV_DEPLOY_ROLE_ARN }}",
            "role-to-assume: ${{ vars.OSA_BUILD_ROLE_ARN }}",
            "deploy-dev is missing required ordering",
        ),
        (
            "  ci-structure:\n    name: CI workflow structure\n    runs-on: ubuntu-latest",
            "  ci-structure:\n    name: CI workflow structure\n    permissions:\n      id-token: write\n    runs-on: ubuntu-latest",
            "non-deployment job 'ci-structure' must not receive an OIDC token permission",
        ),
    ],
)
def test_ci_validator_rejects_unsafe_development_deployment_wiring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    old: str,
    new: str,
    message: str,
) -> None:
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert old in source
    altered_workflow = tmp_path / "ci.yml"
    altered_workflow.write_text(source.replace(old, new), encoding="utf-8")
    monkeypatch.setattr(VALIDATOR, "WORKFLOW", altered_workflow)

    with pytest.raises(SystemExit):
        VALIDATOR.validate()

    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "needs: [deploy-dev, publish-ecr]",
            "needs: [publish-ecr]",
            "verify-dev is missing required ordering",
        ),
        (
            "role-to-assume: ${{ vars.OSA_DEV_VERIFICATION_ROLE_ARN }}",
            "role-to-assume: ${{ vars.OSA_DEV_DEPLOY_ROLE_ARN }}",
            "verify-dev is missing required ordering",
        ),
    ],
)
def test_ci_validator_rejects_unsafe_development_verification_wiring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    old: str,
    new: str,
    message: str,
) -> None:
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert old in source
    altered_workflow = tmp_path / "ci.yml"
    altered_workflow.write_text(source.replace(old, new), encoding="utf-8")
    monkeypatch.setattr(VALIDATOR, "WORKFLOW", altered_workflow)

    with pytest.raises(SystemExit):
        VALIDATOR.validate()

    assert message in capsys.readouterr().err


def test_ci_validator_rejects_publication_that_runs_when_aws_is_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    gate = (
        " && (vars.OSA_AWS_REGION != '' || vars.OSA_BUILD_ROLE_ARN != '' "
        "|| vars.OSA_ECR_REPOSITORY_URI != '')"
    )
    assert gate in source
    altered_workflow = tmp_path / "ci.yml"
    altered_workflow.write_text(source.replace(gate, ""), encoding="utf-8")
    monkeypatch.setattr(VALIDATOR, "WORKFLOW", altered_workflow)

    with pytest.raises(SystemExit):
        VALIDATOR.validate()

    assert "publish-ecr is missing required security or ordering marker" in capsys.readouterr().err


def test_ci_validator_rejects_a_job_defined_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    duplicate = (
        "  grafana-dashboard-validation:\n    name: Stale duplicate\n    runs-on: ubuntu-latest\n\n"
    )
    assert "  backend-tests:\n" in source
    altered_workflow = tmp_path / "ci.yml"
    altered_workflow.write_text(
        source.replace("  backend-tests:\n", duplicate + "  backend-tests:\n", 1), encoding="utf-8"
    )
    monkeypatch.setattr(VALIDATOR, "WORKFLOW", altered_workflow)

    with pytest.raises(SystemExit):
        VALIDATOR.validate()

    assert "job 'grafana-dashboard-validation' is defined more than once" in capsys.readouterr().err
