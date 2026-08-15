#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
APP_NAME=""

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> --app-name <name>

Prints useful environment values derived from an existing Azure Container App.

Required:
  --resource-group <name>   Azure resource group containing the Container App
  --app-name <name>         Azure Container App name
  --help                    Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group)
      [[ $# -ge 2 ]] || fail "Missing value for --resource-group"
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --app-name)
      [[ $# -ge 2 ]] || fail "Missing value for --app-name"
      APP_NAME="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$RESOURCE_GROUP" ]] || fail "--resource-group is required"
[[ -n "$APP_NAME" ]] || fail "--app-name is required"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az containerapp show --resource-group "$RESOURCE_GROUP" --name "$APP_NAME" --output none >/dev/null 2>&1; then
  fail "Container App '$APP_NAME' was not found in resource group '$RESOURCE_GROUP'"
fi

FQDN=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

INGRESS=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --query properties.configuration.ingress.external \
  --output tsv)

echo "AZURE_CONTAINER_APP_NAME=$APP_NAME"
echo "AZURE_CONTAINER_APP_FQDN=${FQDN:-}"
if [[ -n "${FQDN:-}" && "$INGRESS" == "true" ]]; then
  echo "AZURE_CONTAINER_APP_URL=https://$FQDN"
fi