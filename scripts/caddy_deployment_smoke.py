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
    url: str,
    *,
    auth: tuple[str, str] | None = None,
    authorization: str | None = None,
    body: bytes | None = None,
    method: str | None = None,
) -> tuple[int, bytes]:
    headers = {}
    if auth is not None:
        credentials = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    if authorization is not None:
        headers["Authorization"] = authorization
    if body is not None:
        headers["Content-Type"] = "multipart/form-data; boundary=OSA241"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as result:
            return result.status, result.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def assert_basic_challenge(
    url: str,
    *,
    authorization: str,
    method: str = "GET",
    body: bytes | None = None,
) -> None:
    request = urllib.request.Request(
        url, data=body, headers={"Authorization": authorization}, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as result:
            raise AssertionError(f"Expected Caddy Basic Auth challenge, received HTTP {result.status}")
    except urllib.error.HTTPError as error:
        challenge = error.headers.get("WWW-Authenticate", "")
        if error.code != 401 or not challenge.startswith("Basic"):
            raise AssertionError("Request did not receive the Caddy Basic Auth challenge") from None


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
        "OSA_HOSTNAME=http://127.0.0.1",
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


def run_production_browser_journey(caddy_url: str) -> None:
    environment = os.environ.copy()
    environment["E2E_BASE_URL"] = caddy_url
    environment["OSA_CADDY_PUBLIC_DEMO_SMOKE"] = "true"
    result = subprocess.run(
        ["npm", "run", "e2e", "--", "e2e/deployment-demo.spec.ts"],
        cwd=ROOT / "frontend",
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Production Caddy browser sample journey failed")


def verify_development(network: str, auth_block: str) -> None:
    name, caddy_url = start_caddy("development", "false", auth_block, network)
    sample_id = None
    sample_token = None
    try:
        wait_for_status(f"{caddy_url}/", 401)
        wait_for_status(f"{caddy_url}/health/ready", 401)
        wait_for_status(f"{caddy_url}/api/datasets/sample", 401)
        bearer_header = f"Bearer {'x' * 43}"
        assert_basic_challenge(
            f"{caddy_url}/api/datasets/sample", authorization=bearer_header, method="POST", body=b""
        )
        assert_basic_challenge(
            f"{caddy_url}/api/datasets/not-a-token/analytics", authorization=bearer_header
        )
        assert_basic_challenge(
            f"{caddy_url}/api/datasets/abcdefghijklmnopqrstuv.extra/analytics",
            authorization=bearer_header,
        )
        wait_for_status(f"{caddy_url}/", 200, auth=("ci-user", "ci-only"))
        wait_for_status(f"{caddy_url}/api/health", 200, auth=("ci-user", "ci-only"))
        status, sample = response(
            f"{caddy_url}/api/datasets/sample", auth=("ci-user", "ci-only"), body=b"", method="POST"
        )
        if status != 201:
            raise AssertionError("Basic-authenticated dev sample creation was rejected")
        sample_values = json.loads(sample)
        sample_id = sample_values["dataset_id"]
        sample_token = sample_values["token"]
        invalid = urllib.request.Request(
            f"{caddy_url}/api/datasets/{sample_id}/analytics",
            headers={"Authorization": f"Bearer {'x' * 43}"},
        )
        try:
            urllib.request.urlopen(invalid, timeout=3)
        except urllib.error.HTTPError as error:
            if error.code != 401 or not error.headers.get("WWW-Authenticate", "").startswith("Bearer"):
                raise AssertionError("Bearer dataset API request did not reach application token validation") from None
        else:
            raise AssertionError("Invalid dataset bearer token was accepted")
        status, analytics = response(
            f"{caddy_url}/api/datasets/{sample_id}/analytics",
            authorization=f"Bearer {sample_token}",
        )
        if status != 200 or not json.loads(analytics).get("kpis"):
            raise AssertionError("Valid bearer dataset API request did not reach the application")
    finally:
        cleanup_status = 0
        if sample_id and sample_token:
            status, _ = response(
                f"{caddy_url}/api/datasets/{sample_id}",
                authorization=f"Bearer {sample_token}",
                method="DELETE",
            )
            cleanup_status = 0 if status == 204 else 1
        stop_caddy(name)
        if cleanup_status:
            raise AssertionError("Temporary Caddy smoke dataset cleanup failed")


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
        run_production_browser_journey(caddy_url)

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
    print("Development Caddy challenge, production browser sample journey, and server-side upload restriction passed.")


if __name__ == "__main__":
    main()
