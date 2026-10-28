"""Normalize service secret references from Docker Compose rendered JSON."""

from typing import Any


def grafana_is_only_secret_consumer(services: Any, secret_name: str) -> bool:
    """Accept Compose's short-name and expanded object forms for secret mounts."""
    if not isinstance(services, dict):
        return False

    normalized: dict[str, list[tuple[str, str | None]]] = {}
    for service_name, service in services.items():
        if not isinstance(service, dict):
            return False
        mounts = service.get("secrets", [])
        if not isinstance(mounts, list):
            return False
        refs: list[tuple[str, str | None]] = []
        for mount in mounts:
            if isinstance(mount, str):
                refs.append((mount, None))
            elif isinstance(mount, dict) and isinstance(mount.get("source"), str):
                target = mount.get("target")
                if target is not None and not isinstance(target, str):
                    return False
                refs.append((mount["source"], target))
            else:
                return False
        normalized[service_name] = refs

    grafana_refs = normalized.get("grafana", [])
    if len(grafana_refs) != 1:
        return False
    source, target = grafana_refs[0]
    if source != secret_name or target not in (None, secret_name, f"/run/secrets/{secret_name}"):
        return False
    return all(
        ref_source != secret_name
        for service_name, refs in normalized.items()
        if service_name != "grafana"
        for ref_source, _ in refs
    )
