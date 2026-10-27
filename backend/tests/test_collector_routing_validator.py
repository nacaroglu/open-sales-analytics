import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_collector_routing.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "osa_validate_collector_routing", VALIDATOR_PATH
)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)
prometheus_target_up = VALIDATOR.prometheus_target_up


def test_prometheus_internal_collector_target_is_up():
    response = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"job": "otelcol-internal", "instance": "collector:8888"},
                    "value": ["1793116069.77", "1"],
                }
            ]
        },
    }
    assert prometheus_target_up(response, "collector:8888")


def test_prometheus_internal_collector_target_must_be_up_not_merely_present():
    response = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"job": "otelcol-internal", "instance": "collector:8888"},
                    "value": ["1793116069.77", "0"],
                }
            ]
        },
    }
    assert not prometheus_target_up(response, "collector:8888")
    assert not prometheus_target_up(response, "other:8888")
