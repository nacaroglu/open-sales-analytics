#!/usr/bin/env python3
"""Send synthetic OTLP signals and verify their configured backend routes."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1"
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


def main() -> None:
    resource = {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": SERVICE}},
            {"key": "deployment.environment.name", "value": {"stringValue": "ci"}},
            {"key": "service.version", "value": {"stringValue": "synthetic"}},
        ]
    }
    post = lambda signal, body: request(f"{BASE}:4318/v1/{signal}", body)
    post(
        "metrics",
        {"resourceMetrics": [{"resource": resource, "scopeMetrics": [{"scope": {"name": "route-check"}, "metrics": [{"name": "osa_route_validation", "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": [{"asInt": "1", "timeUnixNano": str(time.time_ns()), "attributes": [{"key": "marker", "value": {"stringValue": MARKER}}]}]}}]}]}]},
    )
    post(
        "logs",
        {"resourceLogs": [{"resource": resource, "scopeLogs": [{"scope": {"name": "route-check"}, "logRecords": [{"timeUnixNano": str(time.time_ns()), "severityText": "INFO", "body": {"stringValue": MARKER}}]}]}]},
    )
    post(
        "traces",
        {"resourceSpans": [{"resource": resource, "scopeSpans": [{"scope": {"name": "route-check"}, "spans": [{"traceId": TRACE_ID, "spanId": "0123456789abcdef", "name": MARKER, "kind": 1, "startTimeUnixNano": str(time.time_ns()), "endTimeUnixNano": str(time.time_ns() + 1_000_000)}]}]}]},
    )

    def metric_visible() -> bool:
        query = urllib.parse.urlencode({"query": "osa_route_validation"})
        result = request(f"{BASE}:9090/api/v1/query?{query}")
        return result.get("status") == "success" and bool(result.get("data", {}).get("result"))

    def log_visible() -> bool:
        query = urllib.parse.urlencode({"query": f'{{service_name="{SERVICE}"}}', "limit": "10"})
        result = request(f"{BASE}:3100/loki/api/v1/query_range?{query}")
        return any(MARKER in value for stream in result.get("data", {}).get("result", []) for _, value in stream.get("values", []))

    def trace_visible() -> bool:
        result = request(f"{BASE}:3200/api/traces/{TRACE_ID}")
        return result.get("traceID", "").lower() == TRACE_ID

    wait_for("metrics → Prometheus", metric_visible)
    wait_for("logs → Loki", log_visible)
    wait_for("traces → Tempo", trace_visible)


if __name__ == "__main__":
    try:
        main()
    except (OSError, urllib.error.URLError) as exc:
        print(f"Synthetic route check could not reach a service ({type(exc).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
