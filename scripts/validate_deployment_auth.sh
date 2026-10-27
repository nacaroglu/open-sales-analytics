#!/bin/sh

set -eu

environment="$(printenv OSA_ENVIRONMENT 2>/dev/null || true)"
public_demo_mode="$(printenv PUBLIC_DEMO_MODE 2>/dev/null || true)"
auth_block="$(printenv CADDY_AUTH_BLOCK 2>/dev/null || true)"

case "$environment:$public_demo_mode" in
  development:false)
    case "$auth_block" in
      *"basic_auth"*) ;;
      *)
        echo "CADDY_AUTH_BLOCK must contain a Basic Authentication directive in development." >&2
        exit 1
        ;;
    esac
    ;;
  production:true)
    if [ -n "$auth_block" ]; then
      echo "CADDY_AUTH_BLOCK must be empty in production." >&2
      exit 1
    fi
    ;;
  *)
    echo "OSA_ENVIRONMENT and PUBLIC_DEMO_MODE must be development/false or production/true." >&2
    exit 1
    ;;
esac

if [ "$#" -eq 0 ]; then
  echo "A Caddy command is required after deployment auth validation." >&2
  exit 1
fi

exec "$@"
