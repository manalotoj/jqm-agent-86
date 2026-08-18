#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
STATIC_WEB_APP_NAME="swa-agent86-dev"
SKU="Standard"
SHOW_DEPLOYMENT_TOKEN=false

normalize_static_web_app_location() {
  local requested_location="$1"
  case "$requested_location" in
    westus)
      printf '%s\n' "westus2"
      ;;
    *)
      printf '%s\n' "$requested_location"
      ;;
  esac
}

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates or reuses the Agent 86 Azure Static Web App.

Required:
  --resource-group <name>   Azure resource group that will hold the Static Web App

Optional:
  --location <azure-region> Static Web App location. Defaults to the resource group location.
  --name <name>             Static Web App name (default: $STATIC_WEB_APP_NAME)
  --sku <sku>               Static Web App SKU (default: $SKU)
  --show-deployment-token   Print the deployment token after provisioning
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
    --location)
      [[ $# -ge 2 ]] || fail "Missing value for --location"
      LOCATION="$2"
      shift 2
      ;;
    --name)
      [[ $# -ge 2 ]] || fail "Missing value for --name"
      STATIC_WEB_APP_NAME="$2"
      shift 2
      ;;
    --sku)
      [[ $# -ge 2 ]] || fail "Missing value for --sku"
      SKU="$2"
      shift 2
      ;;
    --show-deployment-token)
      SHOW_DEPLOYMENT_TOKEN=true
      shift
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

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az group show --name "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  fail "Resource group '$RESOURCE_GROUP' was not found"
fi

if [[ -z "$LOCATION" ]]; then
  LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)
fi

[[ -n "$LOCATION" ]] || fail "Could not resolve Azure location"

RAW_LOCATION="$LOCATION"
LOCATION=$(normalize_static_web_app_location "$LOCATION")

if [[ "$RAW_LOCATION" != "$LOCATION" ]]; then
  echo "Static Web Apps are not available in '$RAW_LOCATION'; using '$LOCATION' instead."
fi

echo "Preparing Azure Static Web App '$STATIC_WEB_APP_NAME' in resource group '$RESOURCE_GROUP' (location: $LOCATION)..."

if az staticwebapp show --resource-group "$RESOURCE_GROUP" --name "$STATIC_WEB_APP_NAME" --output none >/dev/null 2>&1; then
  echo "Static Web App already exists; reusing it."
else
  az staticwebapp create \
    --name "$STATIC_WEB_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku "$SKU" \
    --output none
fi

DEFAULT_HOSTNAME=$(az staticwebapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STATIC_WEB_APP_NAME" \
  --query defaultHostname \
  --output tsv)

[[ -n "$DEFAULT_HOSTNAME" ]] || fail "Failed to resolve Static Web App hostname"

echo "Azure Static Web App ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Location                   : $LOCATION"
echo "  Static Web App             : $STATIC_WEB_APP_NAME"
echo "  Default Hostname           : $DEFAULT_HOSTNAME"
echo "  Suggested env values:"
echo "    AZURE_STATIC_WEB_APP_NAME=$STATIC_WEB_APP_NAME"
echo "    AZURE_STATIC_WEB_APP_URL=https://$DEFAULT_HOSTNAME"

if [[ "$SHOW_DEPLOYMENT_TOKEN" == true ]]; then
  DEPLOYMENT_TOKEN=$(az staticwebapp secrets list \
    --resource-group "$RESOURCE_GROUP" \
    --name "$STATIC_WEB_APP_NAME" \
    --query properties.apiKey \
    --output tsv)
  [[ -n "$DEPLOYMENT_TOKEN" ]] || fail "Failed to resolve Static Web App deployment token"
  echo "    AZURE_STATIC_WEB_APP_DEPLOYMENT_TOKEN=$DEPLOYMENT_TOKEN"
fi