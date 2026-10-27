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
