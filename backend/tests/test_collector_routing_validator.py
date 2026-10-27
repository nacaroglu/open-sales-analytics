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
tcp_endpoint_ready = VALIDATOR.tcp_endpoint_ready


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


def test_collector_receiver_readiness_returns_false_while_port_is_refused(monkeypatch):
    def refuse_connection(address, timeout):
        raise ConnectionRefusedError

    monkeypatch.setattr(VALIDATOR.socket, "create_connection", refuse_connection)
    assert not tcp_endpoint_ready("127.0.0.1", 4318)


def test_collector_receiver_readiness_returns_true_when_port_accepts_connections(monkeypatch):
    class ConnectedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        VALIDATOR.socket, "create_connection", lambda _address, timeout: ConnectedSocket()
    )
    assert tcp_endpoint_ready("127.0.0.1", 4318)
