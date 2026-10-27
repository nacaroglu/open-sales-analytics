#!/bin/sh

set -eu

environment="${OSA_ENVIRONMENT-}"
public_demo_mode="${PUBLIC_DEMO_MODE-}"
auth_block="${CADDY_AUTH_BLOCK-}"

case "$environment:$public_demo_mode" in
  development:false)
    if ! parameter_type="$(aws ssm get-parameter \
      --name /osa/dev/caddy/auth \
      --query Parameter.Type \
      --output text \
      --cli-connect-timeout 5 \
      --cli-read-timeout 10 2>/dev/null)" || [ "$parameter_type" != "SecureString" ]; then
      echo "Development Caddy authentication parameter must be a SecureString." >&2
      exit 1
    fi
    if ! auth_block="$(aws ssm get-parameter \
      --name /osa/dev/caddy/auth \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --cli-connect-timeout 5 \
      --cli-read-timeout 10 2>/dev/null)"; then
      echo "Unable to load development Caddy authentication configuration from SSM." >&2
      exit 1
    fi
    case "$auth_block" in
      *basic_auth*) ;;
      *)
        echo "Development Caddy authentication configuration is missing or invalid." >&2
        exit 1
        ;;
    esac
    ;;
  production:true)
    if [ -n "$auth_block" ]; then
      echo "Production Caddy authentication configuration must be empty." >&2
      exit 1
    fi
    ;;
  *)
    echo "OSA_ENVIRONMENT and PUBLIC_DEMO_MODE must be development/false or production/true." >&2
    exit 1
    ;;
esac

export CADDY_AUTH_BLOCK="$auth_block"
exec docker compose --env-file /opt/osa/.env -f /opt/osa/compose.yaml up --remove-orphans
