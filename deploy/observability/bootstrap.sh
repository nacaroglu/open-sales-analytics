#!/bin/bash
set -euo pipefail

umask 077
log() { printf '%s\n' "$1"; }

config_root=/opt/osa/observability
storage_root=/srv/osa-observability
runtime_root=/run/osa-observability
mkdir -p "$config_root" "$storage_root" "$runtime_root"
chmod 0700 "$runtime_root"

# On the supported Nitro instance types the root disk is nvme0n1 and the
# attached telemetry EBS volume is the only other EBS NVMe device.
root_source="$(findmnt -n -o SOURCE /)"
root_device="$(lsblk -ndo PKNAME "$root_source" | head -n1)"
data_device=""
for attempt in $(seq 1 60); do
  for candidate in /dev/nvme*n1; do
    [ -b "$candidate" ] || continue
    [ "$(basename "$candidate")" = "$root_device" ] && continue
    data_device="$candidate"
    break
  done
  [ -n "$data_device" ] && break
  sleep 2
done
if [ -z "$data_device" ]; then
  log "Required telemetry EBS volume is not attached."
  exit 1
fi

if ! blkid "$data_device" >/dev/null 2>&1; then
  mkfs.xfs -f "$data_device" >/dev/null
fi
mkdir -p "$storage_root"
if ! mountpoint -q "$storage_root"; then
  filesystem_uuid="$(blkid -s UUID -o value "$data_device")"
  grep -q "UUID=$filesystem_uuid " /etc/fstab || \
    printf 'UUID=%s %s xfs defaults,nodev,nosuid,noexec,nofail 0 2\n' \
      "$filesystem_uuid" "$storage_root" >> /etc/fstab
  mount "$storage_root"
fi

mkdir -p "$storage_root/prometheus" "$storage_root/loki" "$storage_root/tempo" \
  "$storage_root/grafana" "$storage_root/caddy-data" "$storage_root/caddy-config"
chown 65534:65534 "$storage_root/prometheus"
chown 10001:10001 "$storage_root/loki" "$storage_root/tempo"
chown 472:472 "$storage_root/grafana"

if ! git -C "$config_root/repository" rev-parse --verify HEAD >/dev/null 2>&1 \
  || [ "$(git -C "$config_root/repository" rev-parse HEAD)" != "$OSA_CONFIG_REVISION" ]; then
  rm -rf "$config_root/repository"
  git init -q "$config_root/repository"
  git -C "$config_root/repository" remote add origin \
    https://github.com/nacaroglu/open-sales-analytics.git
  git -C "$config_root/repository" fetch --quiet --depth 1 origin "$OSA_CONFIG_REVISION"
  git -C "$config_root/repository" checkout --quiet --detach FETCH_HEAD
fi
repo="$config_root/repository"
for file in compose.aws.yaml collector.aws.yaml Caddyfile; do
  if [ ! -s "$repo/observability/$file" ]; then
    log "Pinned observability configuration is missing a required file."
    exit 1
  fi
done

if ! grafana_admin_password="$(aws ssm get-parameter \
  --name "$GRAFANA_ADMIN_PARAMETER_NAME" \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text \
  --region "$AWS_REGION" 2>/dev/null)"; then
  log "Grafana administrator credentials could not be retrieved from Parameter Store."
  exit 1
fi
if [ -z "$grafana_admin_password" ] || [ "$grafana_admin_password" = "None" ]; then
  unset grafana_admin_password
  log "Grafana administrator credentials are empty."
  exit 1
fi
printf '%s' "$grafana_admin_password" > "$runtime_root/grafana-admin-password"
unset grafana_admin_password
chmod 0400 "$runtime_root/grafana-admin-password"
chown 472:472 "$runtime_root/grafana-admin-password"

read_otlp_token() {
  local parameter="$1" parameter_type token
  if ! parameter_type="$(aws ssm get-parameter --name "$parameter" --query 'Parameter.Type' \
    --output text --region "$AWS_REGION" 2>/dev/null)" || [ "$parameter_type" != SecureString ]; then
    printf '%s\n' "OTLP authentication parameters must be SecureStrings." >&2
    return 1
  fi
  if ! token="$(aws ssm get-parameter --name "$parameter" --with-decryption \
    --query 'Parameter.Value' --output text --region "$AWS_REGION" 2>/dev/null)"; then
    printf '%s\n' "OTLP authentication configuration could not be retrieved from Parameter Store." >&2
    return 1
  fi
  if [ -z "$token" ] || [[ ! "$token" =~ ^[A-Za-z0-9_-]+$ ]]; then
    unset token
    printf '%s\n' "OTLP authentication configuration is empty or invalid." >&2
    return 1
  fi
  printf '%s' "$token"
  unset token
}

otlp_token_file="$runtime_root/otlp-tokens"
otlp_token_temp="$runtime_root/otlp-tokens.tmp"
trap 'rm -f "$otlp_token_temp"' EXIT
umask 077
read_otlp_token /osa/dev/observability/otlp-token > "$otlp_token_temp"
printf '\n' >> "$otlp_token_temp"
read_otlp_token /osa/prod/observability/otlp-token >> "$otlp_token_temp"
chown root:10001 "$otlp_token_temp"
chmod 0440 "$otlp_token_temp"
mv -f "$otlp_token_temp" "$otlp_token_file"

export OSA_GRAFANA_HOSTNAME
export OSA_GRAFANA_ROOT_URL
export OSA_CONFIG_DIR="$repo/observability"
export OSA_STORAGE_ROOT="$storage_root"
export GRAFANA_ADMIN_SECRET_FILE="$runtime_root/grafana-admin-password"
export OTLP_TOKEN_FILE="$otlp_token_file"
docker compose --project-name osa-observability \
  -f "$repo/observability/compose.aws.yaml" config --quiet
docker compose --project-name osa-observability \
  -f "$repo/observability/compose.aws.yaml" up --detach --remove-orphans

log "OSA observability services started."
