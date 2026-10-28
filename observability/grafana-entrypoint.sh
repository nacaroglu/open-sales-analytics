#!/bin/sh
set -eu

secret_file=/run/secrets/osa_alert_webhook_url
if [ ! -r "$secret_file" ]; then
  printf '%s\n' 'Protected Grafana webhook configuration is unavailable.' >&2
  exit 1
fi

webhook_url="$(cat "$secret_file")"
case "$webhook_url" in
  https://*) ;;
  *)
    unset webhook_url
    printf '%s\n' 'Protected Grafana webhook configuration must use HTTPS.' >&2
    exit 1
    ;;
esac
export OSA_ALERT_WEBHOOK_URL="$webhook_url"
unset webhook_url
exec /run.sh "$@"
