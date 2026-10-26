#!/usr/bin/env python3
"""Exercise the built application through isolated Docker Compose projects."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from shlex import join as shell_join
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_OUTPUT_TIMEOUT = 30
COMPOSE_COMMAND_TIMEOUT = 120
COMPOSE_START_TIMEOUT = 600
COMPOSE_CLEANUP_TIMEOUT = 60
COMPOSE_FILES = (
    "docker-compose.yaml",
    "docker-compose.integration-test.yaml",
    "docker-compose.test-telemetry.yaml",
)
FIXTURE = (
    "order_id,order_date,product_id,product_name,quantity,unit_price\n"
    "A1,2025-01-10,P1,Mug,2,10.00\n"
    "A2,2025-01-11,P2,Bag,1,5.00\n"
)
INVALID_FIXTURE = "not,a,valid\ncsv\n"
BOUNDARY = "osa-compose-" + uuid.uuid4().hex


class IntegrationFailure(RuntimeError):
    pass


def check(condition: bool, case: str, detail: str) -> None:
    if not condition:
        raise IntegrationFailure(f"{case}: {detail}")


def mark(case: str, detail: str) -> None:
    print(f"PASS {case}: {detail}", flush=True)


def http(
    base_url: str,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 10,
) -> tuple[int, dict[str, str], bytes]:
    request = Request(base_url + path, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as response:
        return response.code, dict(response.headers.items()), response.read()


def json_body(response: tuple[int, dict[str, str], bytes], case: str) -> dict:
    status, headers, body = response
    check(
        status == 200 or status == 201,
        case,
        f"expected successful JSON response, got HTTP {status}",
    )
    check("json" in headers.get("Content-Type", "").lower(), case, "response was not JSON")
    try:
        result = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise IntegrationFailure(f"{case}: response body was not valid JSON") from None
    check(isinstance(result, dict), case, "response JSON was not an object")
    return result


def wait_ready(base_url: str, compose: list[str], timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, headers, body = http(base_url, "GET", "/health/ready", timeout=2)
            if status == 200 and "json" in headers.get("Content-Type", "").lower():
                payload = json.loads(body)
                if payload.get("status") == "ready":
                    mark("IT-01", "application became ready within the bounded startup timeout")
                    return
        except (OSError, URLError, json.JSONDecodeError):
            pass
        time.sleep(1)
    diagnostics = compose_output(compose, "ps", "--all")
    logs = compose_output(compose, "logs", "--no-color", "--tail=80")
    raise IntegrationFailure(
        "IT-01: readiness timeout; Compose status and service logs follow\n" + diagnostics + logs
    )


def compose_output(compose: list[str], *args: str) -> str:
    result = bounded_run(
        [*compose, *args],
        timeout=COMPOSE_OUTPUT_TIMEOUT,
        cwd=ROOT,
        env=ACTIVE_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout + result.stderr


def compose_run(
    compose: list[str],
    *args: str,
    check_success: bool = True,
    timeout: int = COMPOSE_COMMAND_TIMEOUT,
) -> str:
    result = bounded_run(
        [*compose, *args],
        timeout=timeout,
        cwd=ROOT,
        env=ACTIVE_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    if check_success and result.returncode:
        raise IntegrationFailure(
            f"Compose command {' '.join(args)} failed with exit code {result.returncode}:\n{output}"
        )
    return output


def bounded_run(args: list[str], *, timeout: int, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        raise IntegrationFailure(
            f"Command exceeded its {timeout}-second timeout: {shell_join(args)}"
        ) from None


def compose_command(project: str) -> list[str]:
    command = ["docker", "compose", "--project-name", project]
    for file in COMPOSE_FILES:
        command.extend(("-f", file))
    return command


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def multipart(csv_text: str, *, currency: str = "USD") -> tuple[bytes, dict[str, str]]:
    boundary = BOUNDARY
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="fixture.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
        f"{csv_text}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="currency"\r\n\r\n'
        f"{currency}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def upload(base_url: str, csv_text: str = FIXTURE) -> dict:
    body, headers = multipart(csv_text)
    response = http(base_url, "POST", "/api/datasets", headers=headers, body=body)
    return json_body(response, "dataset upload")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def openapi_schemas(base_url: str) -> dict:
    global OPENAPI_SCHEMAS
    if OPENAPI_SCHEMAS is None:
        response = http(base_url, "GET", "/openapi.json")
        document = json_body(response, "IT-03 OpenAPI contract")
        schemas = document.get("components", {}).get("schemas")
        check(isinstance(schemas, dict), "IT-03 OpenAPI contract", "component schemas were missing")
        OPENAPI_SCHEMAS = schemas
    return OPENAPI_SCHEMAS


def validate_schema(schema: dict, value: object, schemas: dict, path: str) -> None:
    if "$ref" in schema:
        prefix = "#/components/schemas/"
        reference = schema["$ref"]
        check(
            reference.startswith(prefix),
            "IT-03 OpenAPI contract",
            f"unsupported schema reference at {path}",
        )
        name = reference[len(prefix) :]
        check(name in schemas, "IT-03 OpenAPI contract", f"unknown schema reference at {path}")
        validate_schema(schemas[name], value, schemas, path)
        return
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_schema(option, value, schemas, path)
                return
            except IntegrationFailure:
                continue
        raise IntegrationFailure(
            f"IT-03 OpenAPI contract: response does not match any schema at {path}"
        )
    expected_type = schema.get("type")
    type_checks = {
        "array": lambda item: isinstance(item, list),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, int | float) and not isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "string": lambda item: isinstance(item, str),
    }
    if expected_type in type_checks:
        check(
            type_checks[expected_type](value),
            "IT-03 OpenAPI contract",
            f"unexpected value type at {path}",
        )
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        check(
            not missing,
            "IT-03 OpenAPI contract",
            f"required response fields were missing at {path}",
        )
        for key, property_schema in schema.get("properties", {}).items():
            if key in value:
                validate_schema(property_schema, value[key], schemas, f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            validate_schema(schema["items"], item, schemas, f"{path}[{index}]")


def validate_openapi_response(base_url: str, path: str, payload: dict, module: str) -> None:
    route = f"/api/datasets/{{id}}/{module}"
    document_schemas = openapi_schemas(base_url)
    document = json_body(http(base_url, "GET", "/openapi.json"), "IT-03 OpenAPI contract")
    operation = document.get("paths", {}).get(route, {}).get("get", {})
    response_schema = (
        operation.get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    check(
        isinstance(response_schema, dict),
        "IT-03 OpenAPI contract",
        f"{module} response schema was missing",
    )
    validate_schema(response_schema, payload, document_schemas, f"{module} response")


def dataset_state(compose: list[str]) -> list[dict[str, str | int | bool]]:
    output = compose_run(
        compose,
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "import json; from pathlib import Path; root=Path('/data'); "
        "print(json.dumps(sorted(({ 'path': str(path.relative_to(root)), "
        "'directory': path.is_dir(), 'size': path.stat().st_size, "
        "'mtime_ns': path.stat().st_mtime_ns } for path in root.rglob('*')), "
        "key=lambda item: item['path'])))",
    )
    try:
        state = json.loads(output.strip().splitlines()[-1])
        if isinstance(state, list) and all(isinstance(entry, dict) for entry in state):
            return state
    except (ValueError, IndexError, json.JSONDecodeError):
        pass
    raise IntegrationFailure(
        "Could not inspect dataset artifacts without exposing their names or contents"
    )


def dataset_file_count(compose: list[str]) -> int:
    try:
        return sum(
            1
            for artifact in dataset_state(compose)
            if not artifact["directory"] and str(artifact["path"]).endswith(".duckdb")
        )
    except (KeyError, TypeError):
        raise IntegrationFailure(
            "Could not count datasets without exposing their names or contents"
        ) from None


def verify_module(base_url: str, path: str, token: str, module: str) -> None:
    status, headers, body = http(base_url, "GET", path, headers=auth(token))
    payload = json_body((status, headers, body), f"IT-03 {module} API")
    validate_openapi_response(base_url, path, payload, module)
    if module == "customers":
        check(
            payload.get("module") == module,
            f"IT-03 {module} API",
            "module discriminator was missing",
        )
    check(isinstance(payload.get("range"), dict), f"IT-03 {module} API", "range was missing")
    check(
        isinstance(payload.get("comparison"), dict), f"IT-03 {module} API", "comparison was missing"
    )
    check(isinstance(payload.get("currency"), str), f"IT-03 {module} API", "currency was missing")
    if module == "overview":
        check(
            isinstance(payload.get("kpis"), dict), "IT-03 overview API", "KPI response was missing"
        )
        check(isinstance(payload.get("trend"), list), "IT-03 overview API", "trend was missing")
        check(
            isinstance(payload.get("top_products"), list),
            "IT-03 overview API",
            "top products were missing",
        )
    elif module == "customers":
        check(
            isinstance(payload.get("coverage"), dict), "IT-03 customers API", "coverage was missing"
        )
        check(
            isinstance(payload.get("sections"), dict),
            "IT-03 customers API",
            "sections were missing",
        )
    elif module == "products":
        check(
            isinstance(payload.get("rankings"), dict), "IT-03 products API", "rankings were missing"
        )
        check(isinstance(payload.get("share"), dict), "IT-03 products API", "share was missing")
        check(
            isinstance(payload.get("product_count"), int),
            "IT-03 products API",
            "product count was missing",
        )


def run_telemetry_identity(compose: list[str], sink_dir: Path) -> None:
    compose_run(
        compose,
        "exec",
        "-T",
        "app",
        "env",
        "PYTHONPATH=/app/backend",
        "OSA_ENVIRONMENT=development",
        "OSA_VERSION=integration-test",
        "python",
        "-m",
        "app.telemetry_test_signal",
    )

    expected = {
        "service.name": "open-sales-analytics",
        "service.namespace": "osa",
        "deployment.environment.name": "development",
        "service.version": "integration-test",
    }
    signal_shapes = {
        "traces": ("resourceSpans", "scopeSpans", "spans"),
        "metrics": ("resourceMetrics", "scopeMetrics", "metrics"),
        "logs": ("resourceLogs", "scopeLogs", "logRecords"),
    }
    sink_file = sink_dir / "osa-telemetry.json"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            records = [
                json.loads(line) for line in sink_file.read_text().splitlines() if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            time.sleep(0.5)
            continue

        signals_ready = True
        for signal, (resource_key, scope_key, data_key) in signal_shapes.items():
            resource_signals = [
                resource_signal
                for record in records
                for resource_signal in record.get(resource_key, [])
            ]
            if not resource_signals:
                signals_ready = False
                break
            for resource_signal in resource_signals:
                attributes = {
                    item["key"]: item["value"].get("stringValue")
                    for item in resource_signal.get("resource", {}).get("attributes", [])
                }
                check(attributes == expected, "IT-08", f"{signal} resource identity did not match")
                signal_records = [
                    item
                    for scope in resource_signal.get(scope_key, [])
                    for item in scope.get(data_key, [])
                ]
                if signal == "logs":
                    emitted = any(
                        item.get("eventName") == "osa.synthetic.resource_identity"
                        and item.get("body", {}).get("stringValue")
                        == "osa.synthetic.resource_identity"
                        for item in signal_records
                    )
                else:
                    emitted = any(
                        item.get("name") == "osa.synthetic.resource_identity"
                        for item in signal_records
                    )
                if not emitted:
                    signals_ready = False
                    break
            if not signals_ready:
                break
        if signals_ready:
            mark(
                "IT-08",
                "synthetic trace, metric, and log carried all four configured resource attributes",
            )
            return
        time.sleep(0.5)

    raise IntegrationFailure(
        "IT-08: test Collector did not capture the synthetic trace, metric, and log "
        "with the expected resource attributes"
    )


def frontend_and_sample(base_url: str) -> dict:
    status, headers, body = http(base_url, "GET", "/")
    check(status == 200, "IT-02", f"frontend HTML returned HTTP {status}")
    check(
        "text/html" in headers.get("Content-Type", "").lower(),
        "IT-02",
        "HTML content type was missing",
    )
    html = body.decode("utf-8", errors="replace")
    js = re.search(r'<script[^>]+src="([^"]+\.js)"', html)
    css = re.search(r'<link[^>]+href="([^"]+\.css)"', html)
    check(js is not None, "IT-02", "built JavaScript asset reference was missing")
    check(css is not None, "IT-02", "built CSS asset reference was missing")
    for label, asset_path, content_type in (
        ("JavaScript", js.group(1), "javascript"),
        ("CSS", css.group(1), "text/css"),
    ):
        asset_status, asset_headers, asset_body = http(base_url, "GET", asset_path)
        check(asset_status == 200, "IT-02", f"built {label} returned HTTP {asset_status}")
        check(
            content_type in asset_headers.get("Content-Type", "").lower(),
            "IT-02",
            f"built {label} content type was incorrect",
        )
        check(bool(asset_body), "IT-02", f"built {label} was empty")
    sample = json_body(http(base_url, "POST", "/api/datasets/sample"), "IT-03 sample workflow")
    dataset_id = sample.get("dataset_id")
    token = sample.get("token")
    check(
        isinstance(dataset_id, str) and bool(dataset_id),
        "IT-03 sample workflow",
        "dataset id was missing",
    )
    check(
        isinstance(token, str) and bool(token), "IT-03 sample workflow", "dataset token was missing"
    )
    check(
        isinstance(sample.get("meta"), dict),
        "IT-03 sample workflow",
        "dataset metadata was missing",
    )
    check(
        isinstance(sample.get("initial_summary"), dict),
        "IT-03 sample workflow",
        "initial summary was missing",
    )
    route_status, route_headers, route_body = http(base_url, "GET", f"/d/{dataset_id}")
    check(route_status == 200, "IT-02", f"SPA route returned HTTP {route_status}")
    check(
        "text/html" in route_headers.get("Content-Type", "").lower(),
        "IT-02",
        "SPA route did not return HTML",
    )
    check(route_body == body, "IT-02", "SPA route did not return the same built entry page")
    mark("IT-02", "HTML, built JS/CSS, and SPA route returned with expected content types")
    verify_module(base_url, f"/api/datasets/{dataset_id}/overview", token, "overview")
    verify_module(base_url, f"/api/datasets/{dataset_id}/customers", token, "customers")
    verify_module(base_url, f"/api/datasets/{dataset_id}/products", token, "products")
    mark(
        "IT-03", "sample dataset loaded and Overview, Customer, and Product response shapes passed"
    )
    return sample


def run_self_hosted(base_url: str, compose: list[str]) -> None:
    frontend_and_sample(base_url)

    before = dataset_file_count(compose)
    uploaded = upload(base_url)
    uploaded_id = uploaded.get("dataset_id")
    uploaded_token = uploaded.get("token")
    check(
        isinstance(uploaded_id, str) and isinstance(uploaded_token, str),
        "IT-04",
        "upload omitted dataset access values",
    )
    check(
        dataset_file_count(compose) == before + 1,
        "IT-04",
        "valid upload did not create exactly one dataset",
    )
    protected_path = f"/api/datasets/{uploaded_id}/overview"
    status, _, _ = http(base_url, "GET", protected_path)
    check(status in (401, 403), "IT-04", f"dataset request without token returned HTTP {status}")
    status, _, _ = http(base_url, "GET", protected_path, headers=auth("incorrect-token"))
    check(
        status in (401, 403),
        "IT-04",
        f"dataset request with incorrect token returned HTTP {status}",
    )
    status, response_headers, body = http(
        base_url, "GET", protected_path, headers=auth(uploaded_token)
    )
    check(status == 200, "IT-04", f"valid token request returned HTTP {status}")
    json_body((status, response_headers, body), "IT-04 valid token request")
    mark("IT-04", "valid fixture created a token-protected dataset")

    artifacts_before_invalid = dataset_state(compose)
    body, headers = multipart(INVALID_FIXTURE)
    invalid_status, _, _ = http(base_url, "POST", "/api/datasets", headers=headers, body=body)
    check(invalid_status in (400, 422), "IT-05", f"invalid upload returned HTTP {invalid_status}")
    artifacts_after_invalid = dataset_state(compose)
    check(
        artifacts_after_invalid == artifacts_before_invalid,
        "IT-05",
        "invalid upload changed dataset files, WALs, temporary uploads, or directory state",
    )
    mark("IT-05", "invalid CSV was rejected without creating a dataset")

    deleted_status, _, _ = http(
        base_url,
        "DELETE",
        f"/api/datasets/{uploaded_id}",
        headers=auth(uploaded_token),
    )
    check(deleted_status == 204, "IT-06", f"explicit deletion returned HTTP {deleted_status}")
    after_delete, _, _ = http(
        base_url,
        "GET",
        protected_path,
        headers=auth(uploaded_token),
    )
    check(after_delete == 404, "IT-06", f"deleted dataset remained available (HTTP {after_delete})")

    expiring = upload(base_url)
    expiring_id = expiring.get("dataset_id")
    expiring_token = expiring.get("token")
    check(
        isinstance(expiring_id, str) and isinstance(expiring_token, str),
        "IT-06",
        "expiry fixture upload failed",
    )
    expiry_path = f"/api/datasets/{expiring_id}"
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        status, _, _ = http(base_url, "GET", expiry_path, headers=auth(expiring_token))
        if status == 404:
            break
        check(status == 200, "IT-06", f"expiry poll returned unexpected HTTP {status}")
        time.sleep(0.5)
    check(status == 404, "IT-06", "dataset did not expire within the bounded polling timeout")
    mark(
        "IT-06",
        "missing and incorrect tokens were denied, deletion removed access, and expiry was observed",
    )


def run_public_demo(base_url: str) -> None:
    before = dataset_state_for_demo()
    body, headers = multipart(FIXTURE)
    status, _, _ = http(base_url, "POST", "/api/datasets", headers=headers, body=body)
    check(status == 403, "IT-07", f"public-demo upload returned HTTP {status}")
    after = dataset_state_for_demo()
    check(after == before, "IT-07", "public-demo upload created a dataset")
    sample = json_body(http(base_url, "POST", "/api/datasets/sample"), "IT-07 sample workflow")
    dataset_id = sample.get("dataset_id")
    token = sample.get("token")
    check(
        isinstance(dataset_id, str) and isinstance(token, str),
        "IT-07",
        "public-demo sample omitted access values",
    )
    verify_module(base_url, f"/api/datasets/{dataset_id}/overview", token, "overview")
    mark("IT-07", "public-demo rejected uploads and kept the sample API usable")


def dataset_state_for_demo() -> list[dict[str, str | int | bool]]:
    return dataset_state(ACTIVE_COMPOSE)


def run_project(*, public_demo: bool) -> None:
    global ACTIVE_COMPOSE, ACTIVE_ENV
    project = f"osa-it-{'demo' if public_demo else 'selfhost'}-{uuid.uuid4().hex[:8]}"
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="osa-it-sink-") as sink_dir:
        os.chmod(sink_dir, 0o777)
        compose = compose_command(project)
        ACTIVE_COMPOSE = compose
        environment = os.environ.copy()
        environment.update(
            {
                "COMPOSE_PROJECT_NAME": project,
                "OSA_TEST_TELEMETRY_DIR": sink_dir,
                "OSA_PORT": str(port),
                "DATASET_DIR": "/data",
                "OSA_ENVIRONMENT": "development",
                "OSA_VERSION": "integration-test",
                "DATASET_TTL_SECONDS": "45",
                "PUBLIC_DEMO_MODE": "true" if public_demo else "false",
            }
        )
        ACTIVE_ENV = environment
        try:
            up_args = ["up", "--detach"]
            if not public_demo:
                up_args.append("--build")
            print(
                compose_run(
                    compose,
                    *up_args,
                    timeout=COMPOSE_START_TIMEOUT,
                ),
                end="",
                flush=True,
            )
            wait_ready(base_url, compose)
            if public_demo:
                run_public_demo(base_url)
            else:
                run_telemetry_identity(compose, Path(sink_dir))
                run_self_hosted(base_url, compose)
        except (subprocess.CalledProcessError, IntegrationFailure) as exc:
            print(f"Compose integration failed: {exc}", file=sys.stderr, flush=True)
            print(compose_output(compose, "ps", "--all"), file=sys.stderr, flush=True)
            print(
                compose_output(compose, "logs", "--no-color", "--tail=80"),
                file=sys.stderr,
                flush=True,
            )
            raise
        finally:
            compose_run(
                compose,
                "down",
                "--volumes",
                "--remove-orphans",
                check_success=False,
                timeout=COMPOSE_CLEANUP_TIMEOUT,
            )
            containers = compose_output(compose, "ps", "--all", "-q").strip()
            if containers:
                raise IntegrationFailure("Compose cleanup left a service container behind")
            volumes = bounded_run(
                [
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                ],
                timeout=COMPOSE_OUTPUT_TIMEOUT,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if volumes:
                raise IntegrationFailure("Compose cleanup left a named volume behind")
    check(not Path(sink_dir).exists(), "cleanup", "telemetry output directory remains")
    mark("cleanup", "Compose services, dataset volume, and telemetry output were removed")


ACTIVE_COMPOSE: list[str] = []
ACTIVE_ENV: dict[str, str] = os.environ.copy()
OPENAPI_SCHEMAS: dict | None = None


def main() -> int:
    try:
        run_project(public_demo=False)
        run_project(public_demo=True)
    except (IntegrationFailure, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("Compose integration cases IT-01 through IT-08 passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
