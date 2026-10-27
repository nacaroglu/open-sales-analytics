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
routing_urls = VALIDATOR.routing_urls
synthetic_counter_point = VALIDATOR.synthetic_counter_point
synthetic_counter_query = VALIDATOR.synthetic_counter_query
tempo_trace_contains = VALIDATOR.tempo_trace_contains


def test_routing_urls_support_compose_internal_service_dns():
    assert routing_urls(
        {
            "OSA_ROUTING_COLLECTOR_URL": "http://collector:4318",
            "OSA_ROUTING_PROMETHEUS_URL": "http://prometheus:9090",
            "OSA_ROUTING_LOKI_URL": "http://loki:3100",
            "OSA_ROUTING_TEMPO_URL": "http://tempo:3200",
        }
    ) == {
        "collector": "http://collector:4318",
        "prometheus": "http://prometheus:9090",
        "loki": "http://loki:3100",
        "tempo": "http://tempo:3200",
    }


def test_synthetic_counter_point_has_a_cumulative_start_timestamp():
    assert synthetic_counter_point(1_000_000_000) == {
        "asInt": "1",
        "startTimeUnixNano": "1000000000",
        "timeUnixNano": "1000000001",
        "attributes": [
            {
                "key": "marker",
                "value": {"stringValue": "osa-route-validation-synthetic"},
            }
        ],
    }


def test_synthetic_counter_query_matches_optional_prometheus_total_suffix():
    assert synthetic_counter_query() == '{__name__=~"osa_route_validation(_total)?"}'


def test_tempo_trace_verification_reads_the_otlp_json_trace_response():
    response = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {"traceId": "0123456789ABCDEF0123456789ABCDEF"},
                        ]
                    }
                ]
            }
        ]
    }
    assert tempo_trace_contains(response, "0123456789abcdef0123456789abcdef")
    assert not tempo_trace_contains(response, "ffffffffffffffffffffffffffffffff")


def test_tempo_trace_verification_accepts_legacy_trace_id_response():
    assert tempo_trace_contains(
        {"traceID": "0123456789ABCDEF0123456789ABCDEF"},
        "0123456789abcdef0123456789abcdef",
    )


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
