#!/usr/bin/env python3
"""Validate a protected Grafana webhook URL file without printing its contents."""

from __future__ import annotations

import ipaddress
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

GRAFANA_CONTAINER_UID = 472
MAX_URL_BYTES = 4096
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def validate_webhook_url(value: str) -> str | None:
    if not value:
        return "The protected webhook URL file is empty."
    if len(value.encode("utf-8")) > MAX_URL_BYTES:
        return "The protected webhook URL exceeds the 4096-byte limit."
    if any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return "The webhook URL must not contain whitespace or control characters."
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return "The webhook URL is malformed; provide an HTTPS URL with a valid port."
    if parsed.scheme != "https" or not parsed.netloc or not hostname:
        return "The webhook URL must use HTTPS and include a hostname."
    if parsed.username is not None or parsed.password is not None:
        return "Do not put credentials in URL user-info; use a protected endpoint URL."
    if parsed.fragment:
        return "The webhook URL must not include a fragment."
    host = hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return "The webhook hostname must be an external host."
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not host or any(not _HOST_LABEL.fullmatch(label) for label in host.split(".")):
            return "The webhook URL hostname is invalid."
    else:
        if not address.is_global:
            return "The webhook URL must not target a private or reserved IP address."
    return None


def validate_secret_file(
    configured_path: str,
    *,
    repository_root: Path,
    required_uid: int = GRAFANA_CONTAINER_UID,
) -> str | None:
    if not configured_path:
        return "Set OSA_ALERT_WEBHOOK_URL_FILE to a protected file outside the repository."
    path = Path(configured_path)
    if not path.is_absolute():
        return "OSA_ALERT_WEBHOOK_URL_FILE must be an absolute path outside the repository."
    if path.is_symlink():
        return "The protected webhook URL file must not be a symbolic link."
    try:
        file_stat = path.stat()
        resolved_path = path.resolve(strict=True)
    except OSError:
        return "The protected webhook URL file is missing or unreadable."
    root = repository_root.resolve()
    if resolved_path == root or root in resolved_path.parents:
        return "Store the webhook URL file outside the repository."
    if not stat.S_ISREG(file_stat.st_mode):
        return "The protected webhook URL must be a regular file."
    if stat.S_IMODE(file_stat.st_mode) != 0o400:
        return "Set the protected webhook URL file to mode 0400."
    if file_stat.st_uid != required_uid:
        return f"Set the protected webhook URL file owner to Grafana container UID {required_uid}."
    if file_stat.st_size > MAX_URL_BYTES + 1:
        return "The protected webhook URL exceeds the 4096-byte limit."
    try:
        contents = resolved_path.read_bytes()
        value = contents.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return "The protected webhook URL file is unreadable or not UTF-8."
    if value.endswith("\n"):
        value = value[:-1]
    if "\n" in value or "\r" in value:
        return "The protected webhook URL file must contain one URL only."
    return validate_webhook_url(value)


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    error = validate_secret_file(
        os.environ.get("OSA_ALERT_WEBHOOK_URL_FILE", ""),
        repository_root=repository_root,
    )
    if error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print("Protected Grafana webhook configuration is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
