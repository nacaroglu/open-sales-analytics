#!/usr/bin/env python3
"""Send synthetic OTLP signals and verify their configured backend routes."""

from __future__ import annotations

import base64
import binascii
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
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


def wait_for(label: str, check, diagnostic: Callable[[], str] | None = None) -> None:
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
    detail = f"; last response: {diagnostic()}" if diagnostic is not None else ""
    raise SystemExit(f"Synthetic {label} route was not confirmed ({last_error}){detail}.")


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


def synthetic_counter_point(timestamp_ns: int) -> dict:
    """Build one valid cumulative monotonic Sum data point with fixed attributes."""
    return {
        "asInt": "1",
        "startTimeUnixNano": str(timestamp_ns),
        "timeUnixNano": str(timestamp_ns + 1),
        "attributes": [{"key": "marker", "value": {"stringValue": MARKER}}],
    }


def synthetic_counter_query() -> str:
    """Match the counter name with or without Prometheus' conventional _total suffix."""
    return '{__name__=~"osa_route_validation(_total)?"}'


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


def tempo_trace_contains(result: dict, trace_id: str) -> bool:
    """Find the synthetic trace ID anywhere in Tempo's versioned response wrappers."""

    def normalized(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        lowered = value.lower()
        if len(lowered) == 32 and all(char in "0123456789abcdef" for char in lowered):
            return lowered
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            return None
        return decoded.hex() if len(decoded) == 16 else None

    expected = normalized(trace_id)
    if expected is None:
        return False

    def walk(value: object):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"traceid", "trace_id"}:
                    yield child
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    return any(normalized(value) == expected for value in walk(result))


def tempo_trace_diagnostic(result: dict, trace_id: str) -> str:
    """Return bounded response structure and ID encoding metadata, never raw response data."""
    expected = trace_id.lower()
    trace_id_fields: list[dict[str, object]] = []
    counts = {"resourceSpans": 0, "scopeSpans": 0, "spans": 0, "batches": 0}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for count_key in counts:
                child = value.get(count_key)
                if isinstance(child, list):
                    counts[count_key] += len(child)
            for key, child in value.items():
                if key.lower() in {"traceid", "trace_id"} and len(trace_id_fields) < 8:
                    encoding = "non-string"
                    matches = False
                    if isinstance(child, str):
                        lowered = child.lower()
                        if len(lowered) == 32 and all(
                            char in "0123456789abcdef" for char in lowered
                        ):
                            encoding = "hex"
                            matches = lowered == expected
                        else:
                            try:
                                decoded = base64.b64decode(child, validate=True)
                            except (ValueError, binascii.Error):
                                encoding = "other-string"
                            else:
                                encoding = "base64"
                                matches = len(decoded) == 16 and decoded.hex() == expected
                    trace_id_fields.append({"field": key, "encoding": encoding, "matches": matches})
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return json.dumps(
        {
            "top_level_keys": sorted(result)[:20],
            "wrapper_keys": {
                key: sorted(result[key])[:20]
                for key in ("trace", "batches")
                if isinstance(result.get(key), dict)
            },
            "counts": counts,
            "trace_id_fields": trace_id_fields,
        },
        sort_keys=True,
    )[:1500]


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
                                        "dataPoints": [synthetic_counter_point(time.time_ns())],
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

    last_metric_response = None

    def metric_visible() -> bool:
        nonlocal last_metric_response
        query = urllib.parse.urlencode({"query": synthetic_counter_query()})
        result = request(f"{urls['prometheus']}/api/v1/query?{query}")
        last_metric_response = result
        return result.get("status") == "success" and bool(result.get("data", {}).get("result"))

    def metric_timeout_diagnostic() -> str:
        if last_metric_response is None:
            return "no Prometheus response"
        return json.dumps(
            {
                key: last_metric_response.get(key)
                for key in ("status", "data", "errorType", "error")
                if key in last_metric_response
            },
            sort_keys=True,
        )[:1500]

    def log_visible() -> bool:
        query = urllib.parse.urlencode({"query": f'{{service_name="{SERVICE}"}}', "limit": "10"})
        result = request(f"{urls['loki']}/loki/api/v1/query_range?{query}")
        return any(
            MARKER in value
            for stream in result.get("data", {}).get("result", [])
            for _, value in stream.get("values", [])
        )

    last_trace_response = None

    def trace_visible() -> bool:
        nonlocal last_trace_response
        result = request(f"{urls['tempo']}/api/traces/{TRACE_ID}")
        last_trace_response = result
        return tempo_trace_contains(result, TRACE_ID)

    def trace_timeout_diagnostic() -> str:
        if last_trace_response is None:
            return "no successful Tempo response"
        return tempo_trace_diagnostic(last_trace_response, TRACE_ID)

    def collector_target_up() -> bool:
        query = urllib.parse.urlencode({"query": 'up{job="otelcol-internal"}'})
        result = request(f"{urls['prometheus']}/api/v1/query?{query}")
        return prometheus_target_up(result, "collector:8888")

    wait_for("metrics → Prometheus", metric_visible, metric_timeout_diagnostic)
    wait_for("logs → Loki", log_visible)
    wait_for("traces → Tempo", trace_visible, trace_timeout_diagnostic)
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
