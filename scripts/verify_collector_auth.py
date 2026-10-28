#!/usr/bin/env python3
"""Verify the AWS Collector config enforces bearer auth without AWS credentials."""

from __future__ import annotations

import re
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_CONFIG = ROOT / "observability" / "collector.aws.yaml"
AWS_COMPOSE = ROOT / "observability" / "compose.aws.yaml"
OTLP_TRACE_BODY = b'{"resourceSpans":[]}'


def request_status(url: str, token: str | None) -> int:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=OTLP_TRACE_BODY, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=2) as response:
            return response.status
    except HTTPError as response:
        return response.code


def main() -> None:
    compose = AWS_COMPOSE.read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^\s*image:\s*(otel/opentelemetry-collector-contrib:[^\s]+)\s*$", compose
    )
    if match is None:
        raise SystemExit("AWS Compose must pin the contrib Collector image")
    image = match.group(1)
    if not COLLECTOR_CONFIG.is_file():
        raise SystemExit("AWS Collector authentication config is missing")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        host_port = listener.getsockname()[1]

    container_name = f"osa-collector-auth-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="osa-collector-auth-") as directory:
        temp_root = Path(directory)
        temp_root.chmod(0o755)
        token_file = temp_root / "tokens"
        token_file.write_text("ci-dev-token\nci-prod-token", encoding="utf-8")
        token_file.chmod(0o444)
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--rm",
                    "--name",
                    container_name,
                    "--publish",
                    f"127.0.0.1:{host_port}:4318",
                    "--volume",
                    f"{COLLECTOR_CONFIG}:/etc/otelcol-contrib/config.yaml:ro",
                    "--volume",
                    f"{token_file}:/run/secrets/otlp-token:ro",
                    image,
                    "--config=/etc/otelcol-contrib/config.yaml",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            endpoint = f"http://127.0.0.1:{host_port}/v1/traces"
            deadline = time.monotonic() + 30
            while True:
                try:
                    status = request_status(endpoint, "ci-dev-token")
                    if status != 200:
                        raise SystemExit(
                            "AWS Collector did not accept its configured synthetic token"
                        )
                    break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise SystemExit(
                            "AWS Collector did not become ready for authenticated OTLP"
                        ) from None
                    time.sleep(0.25)

            if request_status(endpoint, None) != 401:
                raise SystemExit("AWS Collector did not reject OTLP without a bearer token")
            if request_status(endpoint, "invalid-ci-token") != 401:
                raise SystemExit("AWS Collector did not reject an invalid OTLP bearer token")
            if request_status(endpoint, "ci-prod-token") != 200:
                raise SystemExit("AWS Collector did not accept its second configured token")
            print("AWS Collector accepted configured tokens and rejected missing/invalid tokens")
        except subprocess.CalledProcessError:
            raise SystemExit("AWS Collector authentication container failed to start") from None
        finally:
            subprocess.run(
                ["docker", "rm", "--force", container_name],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )


if __name__ == "__main__":
    main()
