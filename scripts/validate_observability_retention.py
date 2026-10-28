#!/usr/bin/env python3
"""Offline checks for telemetry retention, limits, and observability EBS policy."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

RETENTION_WINDOW = timedelta(days=7)


def is_expired(timestamp: datetime, now: datetime) -> bool:
    """Return whether a sample/log/trace timestamp is strictly outside the seven-day window."""
    return timestamp < now - RETENTION_WINDOW


def _read(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        errors.append(f"Missing observability configuration: {path}")
        return ""


def _require(text: str, pattern: str, label: str, errors: list[str]) -> None:
    if re.search(pattern, text, flags=re.MULTILINE) is None:
        errors.append(f"{label} is missing or does not match the required bounded value")


def validate_backend_configs(config_dir: Path) -> list[str]:
    """Check the checked-in backend configurations without network or service startup."""
    errors: list[str] = []
    compose = _read(config_dir / "compose.yaml", errors)
    prometheus = _read(config_dir / "prometheus.yaml", errors)
    loki = _read(config_dir / "loki.yaml", errors)
    tempo = _read(config_dir / "tempo.yaml", errors)

    for flag, pattern in (
        ("Prometheus seven-day retention", r"--storage\.tsdb\.retention\.time=7d\b"),
        ("Prometheus TSDB size cap", r"--storage\.tsdb\.retention\.size=10GB\b"),
    ):
        _require(compose, pattern, flag, errors)
    _require(compose, r"prometheus-data:/prometheus\b", "Prometheus persistent data path", errors)
    _require(prometheus, r"global:\s*\n\s+scrape_interval:", "Prometheus config", errors)

    _require(loki, r"retention_period:\s*168h\b", "Loki seven-day retention", errors)
    _require(loki, r"retention_enabled:\s*true\b", "Loki compactor retention", errors)
    _require(loki, r"delete_request_store:\s*filesystem\b", "Loki retention delete store", errors)
    _require(loki, r"ingestion_rate_mb:\s*4\b", "Loki ingestion rate cap", errors)
    _require(loki, r"ingestion_burst_size_mb:\s*6\b", "Loki ingestion burst cap", errors)
    _require(loki, r"max_global_streams_per_user:\s*5000\b", "Loki stream cap", errors)
    _require(compose, r"loki-data:/loki\b", "Loki bounded persistent data path", errors)

    _require(tempo, r"block_retention:\s*168h\b", "Tempo seven-day block retention", errors)
    _require(tempo, r"max_block_bytes:\s*1073741824\b", "Tempo block size cap", errors)
    _require(tempo, r"rate_limit_bytes:\s*1048576\b", "Tempo ingestion rate cap", errors)
    _require(tempo, r"burst_size_bytes:\s*2097152\b", "Tempo ingestion burst cap", errors)
    _require(tempo, r"max_bytes_per_trace:\s*5000000\b", "Tempo trace size cap", errors)
    _require(compose, r"tempo-data:/var/tempo\b", "Tempo bounded persistent data path", errors)
    if re.search(
        r"(?m)^(?:ingester|ingester_client|compactor|compaction|metrics_generator_client):\s*$",
        tempo,
    ):
        errors.append("Tempo config contains removed Tempo 3.x configuration")

    aws_compose_path = config_dir / "compose.aws.yaml"
    if aws_compose_path.exists():
        aws_compose = _read(aws_compose_path, errors)
        for service_path, destination in (
            ("prometheus", "/prometheus"),
            ("loki", "/loki"),
            ("tempo", "/var/tempo"),
        ):
            _require(
                aws_compose,
                rf"\$\{{OSA_STORAGE_ROOT[^\n]*\}}/{service_path}:{re.escape(destination)}\b",
                f"AWS {service_path} EBS-backed data path",
                errors,
            )

    # Verify bounded local storage is used, with no remote object store or archive path.
    _require(loki, r"object_store:\s*filesystem\b", "Loki local storage backend", errors)
    _require(tempo, r"backend:\s*local\b", "Tempo local storage backend", errors)
    if re.search(r"(?im)^\s*(?:s3|gcs|azure|bucket|backup|archive):", loki + tempo):
        errors.append("Telemetry object-store/archive configuration is not allowed")
    return errors


def _resource_block(template: str, logical_name: str) -> str | None:
    lines = template.splitlines()
    target = re.compile(rf"^  {re.escape(logical_name)}:\s*$")
    for index, line in enumerate(lines):
        if target.fullmatch(line):
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= 2:
                    break
                end += 1
            return "\n".join(lines[index:end])
    return None


def validate_ebs_template(path: Path) -> list[str]:
    """Check the #263 logical EBS resources for encryption and delete-on-teardown policy."""
    errors: list[str] = []
    template = _read(path, errors)
    volume = _resource_block(template, "TelemetryVolume")
    if volume is None:
        errors.append("TelemetryVolume resource is required")
        return errors

    _require(volume, r"(?m)^    Type:\s*AWS::EC2::Volume\s*$", "TelemetryVolume type", errors)
    _require(
        volume, r"(?m)^    DeletionPolicy:\s*Delete\s*$", "TelemetryVolume DeletionPolicy", errors
    )
    _require(
        volume,
        r"(?m)^    UpdateReplacePolicy:\s*Delete\s*$",
        "TelemetryVolume UpdateReplacePolicy",
        errors,
    )
    _require(
        volume,
        r"(?m)^      Encrypted:\s*true\s*$",
        "TelemetryVolume Encrypted must be true",
        errors,
    )
    _require(volume, r"(?m)^      Size:\s*100\s*$", "TelemetryVolume bounded size", errors)
    attachment = _resource_block(template, "TelemetryVolumeAttachment")
    if attachment is None:
        errors.append("TelemetryVolumeAttachment resource is required")
    if attachment is not None:
        _require(
            attachment,
            r"VolumeId:\s*!Ref TelemetryVolume\b",
            "TelemetryVolume attachment",
            errors,
        )
        _require(
            attachment,
            r"InstanceId:\s*!Ref ObservabilityInstance\b",
            "TelemetryVolume host attachment",
            errors,
        )
    if re.search(r"AWS::EC2::Snapshot|AWS::Backup::Backup(?:Plan|Selection)|SnapshotId:", template):
        errors.append("Telemetry snapshots and backups are not allowed")
    return errors


def validate_aws_storage_bootstrap(path: Path) -> list[str]:
    """Ensure production data directories are mounted from the dedicated EBS filesystem."""
    errors: list[str] = []
    bootstrap = _read(path, errors)
    _require(
        bootstrap,
        r"(?m)^storage_root=/srv/osa-observability\s*$",
        "AWS telemetry EBS mount path",
        errors,
    )
    _require(bootstrap, r'mountpoint -q "\$storage_root"', "AWS EBS mount check", errors)
    _require(bootstrap, r'mount "\$storage_root"', "AWS EBS mount operation", errors)
    for service in ("prometheus", "loki", "tempo"):
        _require(
            bootstrap,
            rf'"\$storage_root/{service}"',
            f"AWS {service} data directory on EBS",
            errors,
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path("observability"))
    parser.add_argument(
        "--ebs-template", type=Path, default=Path("deploy/cloudformation/osa-observability.yaml")
    )
    parser.add_argument(
        "--bootstrap-script", type=Path, default=Path("deploy/observability/bootstrap.sh")
    )
    args = parser.parse_args()

    errors = validate_backend_configs(args.config_dir)
    if args.ebs_template.exists():
        errors.extend(validate_ebs_template(args.ebs_template))
    else:
        print(
            "EBS template check deferred: deploy/cloudformation/osa-observability.yaml "
            "is supplied by issue #263.",
            file=sys.stderr,
        )
    if args.bootstrap_script.exists():
        errors.extend(validate_aws_storage_bootstrap(args.bootstrap_script))
    else:
        print(
            "AWS storage mount check deferred: deploy/observability/bootstrap.sh "
            "is supplied by issue #263.",
            file=sys.stderr,
        )
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    print("Seven-day telemetry retention and storage-limit checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
