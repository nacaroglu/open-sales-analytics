#!/usr/bin/env python3
"""Send synthetic OTLP signals and verify their configured backend routes."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from urllib.parse import urlsplit

DEFAULT_URLS = {
    "collector": "http://127.0.0.1:4318",
    "prometheus": "http://127.0.0.1:9090",
    "loki": "http://127.0.0.1:3100",
    "tempo": "http://127.0.0.1:3200",
}
SERVICE = "osa-ci-route-validation"
MARKER = "osa-route-validation-synthetic"
TRACE_ID = "0123456789abcdef0123456789abcdef"


def request(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.loads(response.read())


def wait_for(label: str, check) -> None:
    deadline = time.monotonic() + 90
    last_error = "not visible yet"
    while time.monotonic() < deadline:
        try:
            if check():
                print(f"Synthetic {label} route verified.")
                return
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            last_error = type(exc).__name__
        time.sleep(2)
    raise SystemExit(f"Synthetic {label} route was not confirmed ({last_error}).")


def tcp_endpoint_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return whether a TCP receiver accepts connections within the timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def routing_urls(environ: Mapping[str, str]) -> dict[str, str]:
    """Resolve bounded service endpoints for host or in-network synthetic probes."""
    return {
        name: environ.get(f"OSA_ROUTING_{name.upper()}_URL", default).rstrip("/")
        for name, default in DEFAULT_URLS.items()
    }


def prometheus_target_up(result: dict, target: str) -> bool:
    """Return whether Prometheus reports the named scrape target as up."""
    if result.get("status") != "success":
        return False
    rows = result.get("data", {}).get("result", [])
    return any(
        row.get("metric", {}).get("instance") == target
        and isinstance(row.get("value"), list)
        and len(row["value"]) > 1
        and row["value"][1] == "1"
        for row in rows
    )


def main() -> None:
    urls = routing_urls(os.environ)
    collector = urlsplit(urls["collector"])
    wait_for(
        "Collector OTLP receiver readiness",
        lambda: tcp_endpoint_ready(collector.hostname or "127.0.0.1", collector.port or 4318),
    )
    resource = {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": SERVICE}},
            {"key": "deployment.environment.name", "value": {"stringValue": "ci"}},
            {"key": "service.version", "value": {"stringValue": "synthetic"}},
        ]
    }

    def post(signal: str, body: dict) -> dict:
        return request(f"{urls['collector']}/v1/{signal}", body)

    post(
        "metrics",
        {
            "resourceMetrics": [
                {
                    "resource": resource,
                    "scopeMetrics": [
                        {
                            "scope": {"name": "route-check"},
                            "metrics": [
                                {
                                    "name": "osa_route_validation",
                                    "sum": {
                                        "aggregationTemporality": 2,
                                        "isMonotonic": True,
                                        "dataPoints": [
                                            {
                                                "asInt": "1",
                                                "timeUnixNano": str(time.time_ns()),
                                                "attributes": [
                                                    {
                                                        "key": "marker",
                                                        "value": {"stringValue": MARKER},
                                                    }
                                                ],
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )
    post(
        "logs",
        {
            "resourceLogs": [
                {
                    "resource": resource,
                    "scopeLogs": [
                        {
                            "scope": {"name": "route-check"},
                            "logRecords": [
                                {
                                    "timeUnixNano": str(time.time_ns()),
                                    "severityText": "INFO",
                                    "body": {"stringValue": MARKER},
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )
    post(
        "traces",
        {
            "resourceSpans": [
                {
                    "resource": resource,
                    "scopeSpans": [
                        {
                            "scope": {"name": "route-check"},
                            "spans": [
                                {
                                    "traceId": TRACE_ID,
                                    "spanId": "0123456789abcdef",
                                    "name": MARKER,
                                    "kind": 1,
                                    "startTimeUnixNano": str(time.time_ns()),
                                    "endTimeUnixNano": str(time.time_ns() + 1_000_000),
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )

    def metric_visible() -> bool:
        query = urllib.parse.urlencode({"query": "osa_route_validation"})
        result = request(f"{urls['prometheus']}/api/v1/query?{query}")
        return result.get("status") == "success" and bool(result.get("data", {}).get("result"))

    def log_visible() -> bool:
        query = urllib.parse.urlencode({"query": f'{{service_name="{SERVICE}"}}', "limit": "10"})
        result = request(f"{urls['loki']}/loki/api/v1/query_range?{query}")
        return any(
            MARKER in value
            for stream in result.get("data", {}).get("result", [])
            for _, value in stream.get("values", [])
        )

    def trace_visible() -> bool:
        result = request(f"{urls['tempo']}/api/traces/{TRACE_ID}")
        return result.get("traceID", "").lower() == TRACE_ID

    def collector_target_up() -> bool:
        query = urllib.parse.urlencode({"query": 'up{job="otelcol-internal"}'})
        result = request(f"{urls['prometheus']}/api/v1/query?{query}")
        return prometheus_target_up(result, "collector:8888")

    wait_for("metrics → Prometheus", metric_visible)
    wait_for("logs → Loki", log_visible)
    wait_for("traces → Tempo", trace_visible)
    wait_for("otelcol-internal scrape target → Prometheus", collector_target_up)


if __name__ == "__main__":
    try:
        main()
    except (OSError, urllib.error.URLError) as exc:
        print(
            f"Synthetic route check could not reach a service ({type(exc).__name__}).",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
