import os
import re
import subprocess
from pathlib import Path
from textwrap import dedent

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPOSITORY_ROOT / "scripts" / "validate_deployment_auth.sh"
APPLICATION_TEMPLATE = REPOSITORY_ROOT / "deploy" / "cloudformation" / "osa-application.yaml"


def run_preflight(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    runtime_environment = os.environ.copy()
    runtime_environment.update(environment)
    return subprocess.run(
        ["sh", str(PREFLIGHT), "sh", "-c", "printf public-service-started"],
        cwd=REPOSITORY_ROOT,
        env=runtime_environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_development_auth_preflight_allows_a_configured_hash():
    result = run_preflight(
        {
            "OSA_ENVIRONMENT": "development",
            "PUBLIC_DEMO_MODE": "false",
            "CADDY_AUTH_BLOCK": "basic_auth { ci-user $2a$14$hashed-value }",
        }
    )

    assert result.returncode == 0
    assert result.stdout == "public-service-started"


def test_development_auth_preflight_fails_before_start_when_missing_or_empty():
    for auth_block in (None, ""):
        environment = {
            "OSA_ENVIRONMENT": "development",
            "PUBLIC_DEMO_MODE": "false",
        }
        if auth_block is not None:
            environment["CADDY_AUTH_BLOCK"] = auth_block

        result = run_preflight(environment)

        assert result.returncode != 0
        assert "public-service-started" not in result.stdout
        assert "CADDY_AUTH_BLOCK" in result.stderr


def test_production_auth_preflight_allows_only_an_explicit_empty_block():
    result = run_preflight(
        {
            "OSA_ENVIRONMENT": "production",
            "PUBLIC_DEMO_MODE": "true",
            "CADDY_AUTH_BLOCK": "",
        }
    )

    assert result.returncode == 0
    assert result.stdout == "public-service-started"


def test_production_auth_preflight_rejects_auth_without_logging_it():
    marker = "basic_auth { ci-user test-hash-marker }"
    result = run_preflight(
        {
            "OSA_ENVIRONMENT": "production",
            "PUBLIC_DEMO_MODE": "true",
            "CADDY_AUTH_BLOCK": marker,
        }
    )

    assert result.returncode != 0
    assert "public-service-started" not in result.stdout
    assert marker not in result.stdout + result.stderr


def test_auth_preflight_rejects_environment_demo_mode_mismatch():
    result = run_preflight(
        {
            "OSA_ENVIRONMENT": "production",
            "PUBLIC_DEMO_MODE": "false",
            "CADDY_AUTH_BLOCK": "",
        }
    )

    assert result.returncode != 0
    assert "public-service-started" not in result.stdout


def test_ec2_auth_preflight_matches_the_tested_shared_script():
    template = APPLICATION_TEMPLATE.read_text(encoding="utf-8")
    embedded_guard = re.search(
        r"(?ms)^ {14}cat > /opt/osa/validate_deployment_auth\.sh <<'PREFLIGHT'\n"
        r"(?P<body>.*?)^ {14}PREFLIGHT$",
        template,
    )

    assert embedded_guard is not None
    embedded = dedent(embedded_guard.group("body"))
    tracked = PREFLIGHT.read_text(encoding="utf-8")

    def without_blank_lines(source: str) -> str:
        return "\n".join(line.rstrip() for line in source.splitlines() if line.strip())

    assert without_blank_lines(embedded) == without_blank_lines(tracked)
