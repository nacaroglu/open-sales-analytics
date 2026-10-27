#!/usr/bin/env python3
"""Exercise the deployment Caddy auth boundary against the real Compose app."""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CADDY_IMAGE = "caddy:2.10.2@sha256:c3d7ee5d2b11f9dc54f947f68a734c84e9c9666c92c88a7f30b9cba5da182adb"
COMPOSE = [
    "docker",
    "compose",
    "-f",
    "docker-compose.yaml",
    "-f",
    "docker-compose.integration-test.yaml",
]


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Docker deployment-auth smoke command failed")
    return result.stdout.strip()


def response(
    url: str, *, auth: tuple[str, str] | None = None, body: bytes | None = None
) -> tuple[int, bytes]:
    headers = {}
    if auth is not None:
        credentials = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    if body is not None:
        headers["Content-Type"] = "multipart/form-data; boundary=OSA241"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as result:
            return result.status, result.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def wait_for_status(url: str, expected: int, *, auth: tuple[str, str] | None = None) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            status, _ = response(url, auth=auth)
            if status == expected:
                return
        except (OSError, TimeoutError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise AssertionError(f"Caddy did not return HTTP {expected} for {url}")


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def docker_network(app_id: str) -> str:
    networks = json.loads(
        run(["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", app_id])
    )
    if len(networks) != 1:
        raise AssertionError("Compose app must be attached to exactly one test network")
    return next(iter(networks))


def start_caddy(environment: str, demo_mode: str, auth_block: str, network: str) -> tuple[str, str]:
    name = f"osa-241-caddy-{uuid.uuid4().hex[:8]}"
    port = free_port()
    command = [
        "docker",
        "run",
        "--detach",
        "--name",
        name,
        "--network",
        network,
        "--publish",
        f"127.0.0.1:{port}:80",
        "--env",
        "OSA_HOSTNAME=http://localhost",
        "--env",
        f"OSA_ENVIRONMENT={environment}",
        "--env",
        f"PUBLIC_DEMO_MODE={demo_mode}",
        "--env",
        f"CADDY_AUTH_BLOCK={auth_block}",
        "--volume",
        f"{ROOT / 'Caddyfile.deploy'}:/etc/caddy/Caddyfile:ro",
        "--volume",
        f"{ROOT / 'scripts' / 'validate_deployment_auth.sh'}:/usr/local/bin/validate-deployment-auth:ro",
        "--entrypoint",
        "/usr/local/bin/validate-deployment-auth",
        CADDY_IMAGE,
        "caddy",
        "run",
        "--config",
        "/etc/caddy/Caddyfile",
        "--adapter",
        "caddyfile",
    ]
    run(command)
    return name, f"http://127.0.0.1:{port}"


def stop_caddy(name: str) -> None:
    subprocess.run(["docker", "rm", "--force", name], cwd=ROOT, capture_output=True, check=False)


def verify_development(network: str, auth_block: str) -> None:
    name, caddy_url = start_caddy("development", "false", auth_block, network)
    try:
        wait_for_status(f"{caddy_url}/", 401)
        wait_for_status(f"{caddy_url}/api/health", 401)
        wait_for_status(f"{caddy_url}/", 200, auth=("ci-user", "ci-only"))
        wait_for_status(f"{caddy_url}/api/health", 200, auth=("ci-user", "ci-only"))
    finally:
        stop_caddy(name)


def verify_production(network: str) -> None:
    environment = os.environ.copy()
    environment["OSA_ENVIRONMENT"] = "production"
    environment["PUBLIC_DEMO_MODE"] = "true"
    run(COMPOSE + ["up", "--no-build", "--force-recreate", "--detach", "app"], env=environment)
    app_id = run(COMPOSE + ["ps", "-q", "app"])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = run(["docker", "inspect", "--format", "{{.State.Health.Status}}", app_id])
        if status == "healthy":
            break
        if status == "unhealthy":
            raise AssertionError("Public-demo app failed its readiness check")
        time.sleep(0.5)
    else:
        raise AssertionError("Public-demo app did not become healthy")

    name, caddy_url = start_caddy("production", "true", "", network)
    try:
        wait_for_status(f"{caddy_url}/", 200)
        wait_for_status(f"{caddy_url}/api/health", 200)
        status, sample = response(f"{caddy_url}/api/datasets/sample", body=b"")
        if status != 201:
            raise AssertionError("Unauthenticated production Caddy did not allow sample creation")
        sample_values = json.loads(sample)
        analytics_request = urllib.request.Request(
            f"{caddy_url}/api/datasets/{sample_values['dataset_id']}/analytics",
            headers={"Authorization": f"Bearer {sample_values['token']}"},
        )
        with urllib.request.urlopen(analytics_request, timeout=5) as result:
            if result.status != 200:
                raise AssertionError("Sample dataset analytics were not available")

        upload_body = (
            b"--OSA241\r\nContent-Disposition: form-data; name=\"currency\"\r\n\r\nUSD\r\n"
            b"--OSA241\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.csv\"\r\n"
            b"Content-Type: text/csv\r\n\r\nMARKER\r\n--OSA241--\r\n"
        )
        status, upload_response = response(f"{caddy_url}/api/datasets", body=upload_body)
        if status != 403 or json.loads(upload_response)["error"]["code"] != "upload_disabled":
            raise AssertionError("Public-demo upload was not rejected with upload_disabled")
    finally:
        stop_caddy(name)


def main() -> None:
    app_id = run(COMPOSE + ["ps", "-q", "app"])
    if not app_id:
        raise AssertionError("The Compose application must be running before the Caddy smoke test")
    network = docker_network(app_id)
    password_hash = run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "caddy",
            CADDY_IMAGE,
            "hash-password",
            "--plaintext",
            "ci-only",
        ]
    )
    auth_block = f"basic_auth {{\n  ci-user {password_hash}\n}}"
    invalid_development = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--env",
            "OSA_ENVIRONMENT=development",
            "--env",
            "PUBLIC_DEMO_MODE=false",
            "--env",
            "CADDY_AUTH_BLOCK=",
            "--volume",
            f"{ROOT / 'scripts' / 'validate_deployment_auth.sh'}:/usr/local/bin/validate-deployment-auth:ro",
            "--entrypoint",
            "/usr/local/bin/validate-deployment-auth",
            CADDY_IMAGE,
            "caddy",
            "--version",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if invalid_development.returncode == 0:
        raise AssertionError("Caddy must refuse to start in development without an auth block")
    if "public-service-started" in invalid_development.stdout + invalid_development.stderr:
        raise AssertionError("Development auth preflight ran the public command without credentials")

    verify_development(network, auth_block)
    verify_production(network)
    print("Development Caddy challenge, production sample mode, and server-side upload restriction passed.")


if __name__ == "__main__":
    main()
