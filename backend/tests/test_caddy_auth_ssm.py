import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
START_COMPOSE = REPOSITORY_ROOT / "scripts" / "start_osa_compose.sh"
AUTH_PREFLIGHT = REPOSITORY_ROOT / "scripts" / "validate_deployment_auth.sh"
SSM_PARAMETER_NAME = "/osa/dev/caddy/auth"
AUTH_BLOCK = "basic_auth {\n  demo $2a$14$test-hash-marker\n}"
GENERIC_RETRIEVAL_ERROR = "Unable to load development Caddy authentication configuration from SSM."


@pytest.fixture
def command_stubs(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    aws_args = tmp_path / "aws-args"
    docker_auth = tmp_path / "docker-auth"
    capture_path = tmp_path / "capture-path"
    aws = bin_dir / "aws"
    aws.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$OSA_TEST_AWS_ARGS_PATH"\n'
        'case "$*" in\n'
        '  *"--query Parameter.Type"*) printf "%s" "${OSA_TEST_PARAMETER_TYPE-SecureString}" ;;\n'
        "  *)\n"
        '    if [ "${OSA_TEST_AWS_STATUS-0}" -ne 0 ]; then\n'
        '      printf "%s" "${OSA_TEST_AWS_ERROR-}" >&2\n'
        '      exit "$OSA_TEST_AWS_STATUS"\n'
        "    fi\n"
        '    printf "%s" "${OSA_TEST_AWS_RESULT-}"\n'
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf "%s" "${CADDY_AUTH_BLOCK-<unset>}" > "$OSA_TEST_DOCKER_AUTH_PATH"\n'
        'printf "%s" "compose-started"\n',
        encoding="utf-8",
    )
    for executable in (aws, docker):
        executable.chmod(0o755)
    return {
        "aws_args": aws_args,
        "bin_dir": bin_dir,
        "capture_path": capture_path,
        "docker_auth": docker_auth,
    }


def run_start_script(command_stubs, tmp_path, **overrides):
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{command_stubs['bin_dir']}:{environment['PATH']}",
            "OSA_ENVIRONMENT": "development",
            "PUBLIC_DEMO_MODE": "false",
            "OSA_TEST_AWS_ARGS_PATH": str(command_stubs["aws_args"]),
            "OSA_TEST_DOCKER_AUTH_PATH": str(command_stubs["docker_auth"]),
        }
    )
    environment.update(overrides)
    return subprocess.run(
        ["sh", str(START_COMPOSE)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_development_start_fetches_decrypted_auth_into_compose_environment(command_stubs, tmp_path):
    result = run_start_script(
        command_stubs,
        tmp_path,
        OSA_TEST_AWS_RESULT=AUTH_BLOCK,
    )

    assert result.returncode == 0
    assert result.stdout == "compose-started"
    assert result.stderr == ""
    assert command_stubs["docker_auth"].read_text(encoding="utf-8") == AUTH_BLOCK
    aws_args = command_stubs["aws_args"].read_text(encoding="utf-8")
    assert f"--name {SSM_PARAMETER_NAME}" in aws_args
    assert "--with-decryption" in aws_args
    assert "--query Parameter.Type" in aws_args
    assert aws_args.count(f"--name {SSM_PARAMETER_NAME}") == 2
    assert AUTH_BLOCK not in result.stdout + result.stderr + aws_args


@pytest.mark.parametrize(
    ("aws_result", "aws_status", "aws_error"),
    [
        ("", "0", ""),
        ("not-an-auth-block", "0", ""),
        ("", "1", "AWS error leaked secret-marker"),
    ],
)
def test_development_start_fails_closed_without_leaking_ssm_errors(
    command_stubs, tmp_path, aws_result, aws_status, aws_error
):
    result = run_start_script(
        command_stubs,
        tmp_path,
        OSA_TEST_AWS_RESULT=aws_result,
        OSA_TEST_AWS_STATUS=aws_status,
        OSA_TEST_AWS_ERROR=aws_error,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert GENERIC_RETRIEVAL_ERROR in result.stderr or (
        "Development Caddy authentication configuration is missing or invalid." in result.stderr
    )
    assert "secret-marker" not in result.stdout + result.stderr
    assert not command_stubs["docker_auth"].exists()


def test_development_start_rejects_a_plain_string_parameter(command_stubs, tmp_path):
    result = run_start_script(
        command_stubs,
        tmp_path,
        OSA_TEST_PARAMETER_TYPE="String",
        OSA_TEST_AWS_RESULT=AUTH_BLOCK,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "Development Caddy authentication parameter must be a SecureString.\n"
    assert "--with-decryption" not in command_stubs["aws_args"].read_text(encoding="utf-8")
    assert not command_stubs["docker_auth"].exists()


def test_production_start_never_calls_ssm_and_keeps_auth_empty(command_stubs, tmp_path):
    result = run_start_script(
        command_stubs,
        tmp_path,
        OSA_ENVIRONMENT="production",
        PUBLIC_DEMO_MODE="true",
        CADDY_AUTH_BLOCK="",
    )

    assert result.returncode == 0
    assert result.stdout == "compose-started"
    assert result.stderr == ""
    assert not command_stubs["aws_args"].exists()
    assert command_stubs["docker_auth"].read_text(encoding="utf-8") == ""


def test_caddy_config_failure_is_generic_before_starting_the_listener(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    caddy = bin_dir / "caddy"
    caddy.write_text(
        "#!/bin/sh\n"
        'if [ "${1-}" = "validate" ]; then\n'
        '  printf "%s" "hash-secret-marker" >&2\n'
        "  exit 1\n"
        "fi\n"
        'printf "%s" "public-listener-started"\n',
        encoding="utf-8",
    )
    caddy.chmod(0o755)
    result = subprocess.run(
        ["sh", str(AUTH_PREFLIGHT), "caddy", "run"],
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "OSA_ENVIRONMENT": "development",
            "PUBLIC_DEMO_MODE": "false",
            "CADDY_AUTH_BLOCK": "basic_auth { user hash-secret-marker }",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Caddy configuration is invalid" in result.stderr
    assert "hash-secret-marker" not in result.stdout + result.stderr
    assert "public-listener-started" not in result.stdout
