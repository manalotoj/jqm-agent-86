#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP=""
LOCATION=""
NAME="appcs-agent86-dev"

usage() {
  cat <<EOF
Usage: $(basename "$0") --resource-group <name> --location <region> [--name <name>]

Creates Azure App Configuration and initializes non-secret Agent 86 runtime controls.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$RESOURCE_GROUP" && -n "$LOCATION" ]] || { usage >&2; exit 2; }

if ! az appconfig show --name "$NAME" --resource-group "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  az appconfig create --name "$NAME" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --sku Free --output none
fi

# Values deliberately contain only operational controls; never place credentials here.
# Do not overwrite an operator's runtime choice on a later infrastructure reconciliation.
ensure_default() {
  local key="$1"
  local value="$2"
  if ! az appconfig kv show --name "$NAME" --key "$key" --output none >/dev/null 2>&1; then
    az appconfig kv set --name "$NAME" --key "$key" --value "$value" --yes --output none
  fi
}

ensure_default agent86:backend:log_level INFO
ensure_default agent86:frontend:log_level WARN
ensure_default agent86:frontend:telemetry_enabled true

ENDPOINT=$(az appconfig show --name "$NAME" --resource-group "$RESOURCE_GROUP" --query endpoint --output tsv)
printf 'App Configuration: %s\nEndpoint: %s\n' "$NAME" "$ENDPOINT"