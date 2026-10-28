"""Read-only checks for the private Collector and environment OTLP token parameter."""

from __future__ import annotations

import ipaddress
import subprocess
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

COLLECTOR_STACK = "osa-observability"
COLLECTOR_ENDPOINT_OUTPUT = "CollectorPrivateEndpoint"
OTLP_PARAMETERS = {
    "development": "/osa/dev/observability/otlp-token",
    "production": "/osa/prod/observability/otlp-token",
}


class OtlpPreflightError(RuntimeError):
    """A safe preflight failure with no AWS response or secret value."""


def _run(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    step: str,
) -> str:
    try:
        result = runner(list(command), capture_output=True, text=True, check=False)
    except OSError as exc:
        raise OtlpPreflightError(f"{step} could not start ({type(exc).__name__}).") from None
    if result.returncode != 0:
        raise OtlpPreflightError(f"{step} failed (exit {result.returncode}).")
    return result.stdout.strip()


def _validate_endpoint(endpoint: str) -> None:
    try:
        parsed = urlsplit(endpoint)
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        raise OtlpPreflightError(
            "The private Collector endpoint is missing or malformed."
        ) from None
    if (
        parsed.scheme != "http"
        or address.version != 4
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
        or port != 4318
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise OtlpPreflightError("The private Collector endpoint is missing or malformed.")


def validate_otlp_prerequisites(
    region: str,
    environment: str,
    *,
    runner: CommandRunner = subprocess.run,
) -> None:
    """Verify the private endpoint and token type before changing an app stack.

    The SSM query requests metadata only; it never decrypts or prints the token.
    """
    parameter = OTLP_PARAMETERS.get(environment)
    if parameter is None:
        raise OtlpPreflightError("The application environment is missing or unsupported.")

    endpoint = _run(
        runner,
        [
            "aws",
            "cloudformation",
            "describe-stacks",
            "--stack-name",
            COLLECTOR_STACK,
            "--query",
            "Stacks[0].Outputs[?OutputKey=='CollectorPrivateEndpoint'].OutputValue | [0]",
            "--output",
            "text",
            "--region",
            region,
        ],
        step="Private Collector endpoint preflight",
    )
    _validate_endpoint(endpoint)

    parameter_type = _run(
        runner,
        [
            "aws",
            "ssm",
            "get-parameter",
            "--name",
            parameter,
            "--query",
            "Parameter.Type",
            "--output",
            "text",
            "--region",
            region,
        ],
        step="OTLP authentication parameter preflight",
    )
    if parameter_type != "SecureString":
        raise OtlpPreflightError(
            "The environment OTLP authentication parameter must exist as a SecureString."
        )
