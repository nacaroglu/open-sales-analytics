from scripts.validate_collector_routing import prometheus_target_up


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
