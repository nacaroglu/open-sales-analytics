#!/usr/bin/env bash
set -euo pipefail
set +x

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"
validator="scripts/validate_alert_webhook_config.py"

if [[ -z "${OSA_ALERT_WEBHOOK_URL_FILE:-}" ]]; then
  python3 "$validator"
elif [[ -r "$OSA_ALERT_WEBHOOK_URL_FILE" ]]; then
  python3 "$validator"
else
  sudo env OSA_ALERT_WEBHOOK_URL_FILE="$OSA_ALERT_WEBHOOK_URL_FILE" python3 "$validator"
fi

exec docker compose -f observability/compose.yaml "$@"
