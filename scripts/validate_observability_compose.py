#!/usr/bin/env python3
"""Validate the rendered, standalone local observability Compose project."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from compose_secret_contract import grafana_is_only_secret_consumer


def fail(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


try:
    compose: dict[str, Any] = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    fail("Compose output is not valid JSON")

expected_services = {"collector", "prometheus", "loki", "tempo", "grafana"}
services = compose.get("services")
require(isinstance(services, dict), "Compose services must be an object")
require(
    set(services) == expected_services,
    "Observability project must contain exactly its five services",
)
require(compose.get("name") == "osa-observability", "Observability project name must stay isolated")

expected_volumes = {"prometheus-data", "loki-data", "tempo-data", "grafana-data"}
volumes = compose.get("volumes")
require(isinstance(volumes, dict), "Compose must declare named data volumes")
require(
    set(volumes) == expected_volumes, "Only the four observability data volumes may be declared"
)
for name, volume in volumes.items():
    require(
        isinstance(volume, dict)
        and volume.get("name") == f"osa-observability_{name}"
        and not volume.get("external", False),
        "Data volumes must be owned by the observability Compose project",
    )

networks = compose.get("networks")
require(
    isinstance(networks, dict) and set(networks) == {"observability", "webhook-egress"},
    "Private service networking and one dedicated Grafana webhook egress network are required",
)
require(
    networks["observability"].get("internal") is True
    and networks["observability"].get("name") == "osa-observability_observability",
    "The observability network must be private and owned by the observability project",
)
require(
    networks["webhook-egress"].get("name") == "osa-observability_webhook-egress"
    and not networks["webhook-egress"].get("internal", False),
    "The dedicated Grafana webhook egress network must be external and project-owned",
)

secrets = compose.get("secrets")
require(
    isinstance(secrets, dict) and set(secrets) == {"osa_alert_webhook_url"},
    "Only the protected Grafana webhook URL file may be mounted as an observability secret",
)
webhook_file = secrets["osa_alert_webhook_url"].get("file")
repository_root = Path(__file__).resolve().parents[1]
require(
    isinstance(webhook_file, str)
    and Path(webhook_file).is_absolute()
    and repository_root not in Path(webhook_file).resolve().parents,
    "The webhook URL file must be an absolute external path, never part of the checkout",
)

expected_images = {
    "collector": "otel/opentelemetry-collector-contrib:0.161.0",
    "prometheus": "prom/prometheus:v3.14.0",
    "loki": "grafana/loki:3.7.8",
    "tempo": "grafana/tempo:3.1.1",
    "grafana": "grafana/grafana:13.2.4",
}
allowed_host_targets = {
    "collector": {4317, 4318},
    "grafana": {3000},
    "prometheus": {9090},
    "loki": {3100},
    "tempo": {3200},
}

used_volumes: set[str] = set()
for name, service in services.items():
    require(isinstance(service, dict), f"Service {name} must be an object")
    require("build" not in service, f"Service {name} must use a published image")
    require(
        service.get("image") == expected_images[name],
        f"Service {name} must use its explicit release image",
    )
    require(
        service.get("networks")
        == (
            {"observability": None, "webhook-egress": None}
            if name == "grafana"
            else {"observability": None}
        ),
        f"Service {name} has an unapproved observability or egress network",
    )
    require(
        "depends_on" not in service, f"Service {name} must not depend on the application project"
    )

    for port in service.get("ports", []):
        require(
            port.get("host_ip") == "127.0.0.1", f"Service {name} publishes a port outside loopback"
        )
        require(
            int(port.get("target", -1)) in allowed_host_targets[name],
            f"Service {name} publishes an unapproved host port",
        )

    for mount in service.get("volumes", []):
        require(isinstance(mount, dict), f"Service {name} has a malformed mount")
        if mount.get("type") == "volume":
            source = mount.get("source")
            require(
                source in expected_volumes, f"Service {name} mounts a volume outside this project"
            )
            used_volumes.add(source)
        elif mount.get("type") == "bind":
            require(
                mount.get("read_only") is True,
                f"Service {name} has a writable configuration bind mount",
            )
        else:
            fail(f"Service {name} has an unsupported mount type")

require(
    used_volumes == expected_volumes,
    "Every declared data volume must be mounted by an observability service",
)
grafana_environment = services["grafana"].get("environment", {})
require(
    isinstance(grafana_environment, dict)
    and bool(grafana_environment.get("GF_SECURITY_ADMIN_PASSWORD"))
    and grafana_environment.get("GF_AUTH_ANONYMOUS_ENABLED") == "false"
    and grafana_environment.get("GF_SERVER_ROOT_URL"),
    "Grafana must require an admin password, disable anonymous access, and configure its public root URL",
)
require(
    "OSA_ALERT_WEBHOOK_URL" not in grafana_environment,
    "The webhook URL must be read from a protected file, not stored in container environment metadata",
)
grafana_entrypoint = " ".join(str(item) for item in services["grafana"].get("entrypoint", []))
require(
    "osa-grafana-entrypoint.sh" in grafana_entrypoint,
    "Grafana must load its webhook URL through the secret-reading entrypoint",
)
require(
    grafana_is_only_secret_consumer(services, "osa_alert_webhook_url"),
    "Grafana alone must mount the protected webhook URL secret",
)

for service in services.values():
    image = service["image"]
    require(
        "@sha256:" in image or re.search(r":[A-Za-z0-9][A-Za-z0-9._-]*$", image) is not None,
        "Every image must use an explicit version or digest",
    )
    require(not image.endswith(":latest"), "Mutable latest image tags are not allowed")

print("Standalone observability Compose project invariants passed.")
