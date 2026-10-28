#!/usr/bin/env python3
"""Offline structural checks for provisioned Grafana data sources and dashboard."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASOURCES = ROOT / "observability/provisioning/datasources/datasources.yaml"
PROVIDER = ROOT / "observability/provisioning/dashboards/dashboards.yaml"
DASHBOARD = ROOT / "observability/dashboards/osa-operations.json"
ROWS = (
    "Release identity",
    "Traffic and reliability",
    "Dataset workflow",
    "Analytics",
    "Runtime and capacity",
)
REQUIRED_PANELS = {
    "Service, environment, and deployed version",
    "Application uptime and start count",
    "Release identity samples",
    "Request rate",
    "5xx error rate",
    "Request latency p50 / p95 / p99",
    "Active requests",
    "Sample and upload attempts by outcome",
    "Internal dataset creation failures",
    "Processing duration p50 / p95 / p99",
    "Rows processed",
    "Active temporary datasets",
    "Dataset cleanup failures",
    "Overview / Customer / Product request rate",
    "Analytics failures by module",
    "Analytics latency p50 / p95 / p99",
    "DuckDB duration and failures by bounded operation",
    "Process CPU utilization",
    "Process memory usage",
    "Temporary-storage free space",
    "Observability disk usage",
    "Collector export failures and dropped telemetry",
}
FILTERS = ("deployment_environment_name=", "service_version")


def fail(message: str) -> None:
    print(f"Grafana provisioning validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read {path.relative_to(ROOT)} ({type(exc).__name__})")


datasources = read_text(DATASOURCES)
for expected in (
    "name: Prometheus",
    "uid: osa-prometheus",
    "type: prometheus",
    "url: http://prometheus:9090",
    "name: Loki",
    "uid: osa-loki",
    "type: loki",
    "url: http://loki:3100",
    "name: Tempo",
    "uid: osa-tempo",
    "type: tempo",
    "url: http://tempo:3200",
):
    require(expected in datasources, f"data-source provisioning is missing {expected!r}")
require(
    not re.search(
        r"(?im)^\s*(?:basicAuth|basicAuthUser|user|password|secureJsonData|token):", datasources
    ),
    "data-source provisioning must not contain credentials",
)
provider = read_text(PROVIDER)
for expected in (
    "apiVersion: 1",
    "name: osa-operations",
    "folder: OSA",
    "type: file",
    "path: /var/lib/grafana/dashboards",
):
    require(expected in provider, f"dashboard provider is missing {expected!r}")

try:
    dashboard: dict[str, Any] = json.loads(read_text(DASHBOARD))
except json.JSONDecodeError as exc:
    fail(f"dashboard is invalid JSON at line {exc.lineno}")
require(dashboard.get("uid") == "osa-operations", "dashboard UID must stay stable")
require(dashboard.get("title") == "OSA Operations", "dashboard title must be OSA Operations")
panels = dashboard.get("panels")
require(isinstance(panels, list), "dashboard panels must be a list")
rows = [
    panel.get("title") for panel in panels if isinstance(panel, dict) and panel.get("type") == "row"
]
require(tuple(rows) == ROWS, "dashboard must contain the five required rows in spec order")
visual_panels = [
    panel for panel in panels if isinstance(panel, dict) and panel.get("type") != "row"
]
titles = {panel.get("title") for panel in visual_panels}
missing_panels = REQUIRED_PANELS - titles
require(not missing_panels, f"dashboard is missing required panels: {sorted(missing_panels)}")
row_panels = {
    "Release identity": {
        "Service, environment, and deployed version",
        "Application uptime and start count",
        "Release identity samples",
    },
    "Traffic and reliability": {
        "Request rate",
        "5xx error rate",
        "Request latency p50 / p95 / p99",
        "Active requests",
    },
    "Dataset workflow": {
        "Sample and upload attempts by outcome",
        "Internal dataset creation failures",
        "Processing duration p50 / p95 / p99",
        "Rows processed",
        "Active temporary datasets",
        "Dataset cleanup failures",
    },
    "Analytics": {
        "Overview / Customer / Product request rate",
        "Analytics failures by module",
        "Analytics latency p50 / p95 / p99",
        "DuckDB duration and failures by bounded operation",
    },
    "Runtime and capacity": {
        "Process CPU utilization",
        "Process memory usage",
        "Temporary-storage free space",
        "Observability disk usage",
        "Collector export failures and dropped telemetry",
    },
}
row_headers = [panel for panel in panels if isinstance(panel, dict) and panel.get("type") == "row"]
for index, row in enumerate(row_headers):
    start = row.get("gridPos", {}).get("y", -1)
    end = (
        row_headers[index + 1].get("gridPos", {}).get("y", float("inf"))
        if index + 1 < len(row_headers)
        else float("inf")
    )
    titles_in_row = {
        panel.get("title")
        for panel in visual_panels
        if start < panel.get("gridPos", {}).get("y", -1) < end
    }
    require(
        titles_in_row == row_panels[row["title"]],
        f"row {row['title']!r} must contain its specified panels",
    )

variables = {item.get("name"): item for item in dashboard.get("templating", {}).get("list", [])}
environment = variables.get("environment", {})
require(environment.get("type") == "custom", "environment must be a fixed custom variable")
env_values = {option.get("value") for option in environment.get("options", [])}
require(
    env_values == {"development", "production"},
    "environment must be limited to development and production",
)
version = variables.get("deployed_version", {})
require(version.get("type") == "query", "deployed_version must be populated from telemetry")
require(
    "label_values(" in str(version.get("query")),
    "deployed_version must query observed telemetry labels",
)
require(
    "service_version" in str(version.get("query")),
    "deployed_version must query the service version label",
)

for panel in visual_panels:
    title = str(panel.get("title", ""))
    description = str(panel.get("description", "")).lower()
    field_defaults = panel.get("fieldConfig", {}).get("defaults", {})
    require(
        "no data" in description and "not" in description and "zero" in description,
        f"panel {title!r} must explain that missing data is not zero",
    )
    require(bool(field_defaults.get("noValue")), f"panel {title!r} must label null values")
    if (
        title == "Observability disk usage"
        or title == "Collector export failures and dropped telemetry"
    ):
        continue
    targets = panel.get("targets", [])
    require(bool(targets), f"application panel {title!r} must have a query")
    for target in targets:
        expression = str(target.get("expr", ""))
        require(
            all(filter_name in expression for filter_name in FILTERS),
            f"application panel {title!r} must filter environment and deployed version",
        )
    links = panel.get("links", [])
    link_text = " ".join(str(link.get("url", "")) for link in links)
    require(
        "osa-loki" in link_text and "osa-tempo" in link_text,
        f"application panel {title!r} needs Loki and Tempo links",
    )
    require(
        "${environment}" in link_text and "${deployed_version" in link_text,
        f"panel links for {title!r} must preserve selected filters",
    )

annotations = dashboard.get("annotations", {}).get("list", [])
deployment_annotations = [
    item for item in annotations if item.get("name") == "Application start / deployment activity"
]
require(
    len(deployment_annotations) == 1, "dashboard must provision application deployment annotations"
)
annotation_expr = str(deployment_annotations[0].get("expr", ""))
require(
    all(filter_name in annotation_expr for filter_name in FILTERS),
    "deployment annotations must apply both dashboard filters",
)

print("Grafana data sources, dashboard structure, filters, links, and no-data behavior passed.")
