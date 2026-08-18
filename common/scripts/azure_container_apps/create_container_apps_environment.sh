#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
WORKSPACE_NAME="law-agent86-dev"
ENVIRONMENT_NAME="acae-agent86-dev"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates or reuses the shared Agent 86 Log Analytics workspace and Azure
Container Apps environment.

Required:
  --resource-group <name>    Azure resource group that will hold the resources

Optional:
  --location <azure-region>  Resource location. Defaults to the resource group location.
  --workspace-name <name>    Log Analytics workspace name (default: $WORKSPACE_NAME)
  --environment-name <name>  Container Apps environment name (default: $ENVIRONMENT_NAME)
  --help                     Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

register_provider_if_needed() {
  local namespace="$1"
  local state

  state=$(az provider show --namespace "$namespace" --query registrationState --output tsv 2>/dev/null || echo "")
  if [[ "$state" == "Registered" ]]; then
    return 0
  fi

  echo "Registering Azure provider '$namespace'..."
  az provider register --namespace "$namespace" --wait --output none
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
    --workspace-name)
      [[ $# -ge 2 ]] || fail "Missing value for --workspace-name"
      WORKSPACE_NAME="$2"
      shift 2
      ;;
    --environment-name)
      [[ $# -ge 2 ]] || fail "Missing value for --environment-name"
      ENVIRONMENT_NAME="$2"
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

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az group show --name "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  fail "Resource group '$RESOURCE_GROUP' was not found"
fi

if [[ -z "$LOCATION" ]]; then
  LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)
fi

[[ -n "$LOCATION" ]] || fail "Could not resolve Azure location"

register_provider_if_needed "Microsoft.App"
register_provider_if_needed "Microsoft.OperationalInsights"

echo "Preparing Container Apps shared resources in resource group '$RESOURCE_GROUP' (location: $LOCATION)..."

if az monitor log-analytics workspace show --resource-group "$RESOURCE_GROUP" --workspace-name "$WORKSPACE_NAME" --output none >/dev/null 2>&1; then
  echo "Log Analytics workspace already exists; reusing it."
else
  echo "Creating Log Analytics workspace '$WORKSPACE_NAME'..."
  az monitor log-analytics workspace create \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$WORKSPACE_NAME" \
    --location "$LOCATION" \
    --output none
fi

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --query customerId \
  --output tsv)

WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --query primarySharedKey \
  --output tsv)

[[ -n "$WORKSPACE_ID" ]] || fail "Failed to resolve workspace ID"
[[ -n "$WORKSPACE_KEY" ]] || fail "Failed to resolve workspace key"

if az containerapp env show --resource-group "$RESOURCE_GROUP" --name "$ENVIRONMENT_NAME" --output none >/dev/null 2>&1; then
  echo "Container Apps environment already exists; reusing it."
else
  echo "Creating Container Apps environment '$ENVIRONMENT_NAME'..."
  az containerapp env create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ENVIRONMENT_NAME" \
    --location "$LOCATION" \
    --logs-workspace-id "$WORKSPACE_ID" \
    --logs-workspace-key "$WORKSPACE_KEY" \
    --output none
fi

DEFAULT_DOMAIN=$(az containerapp env show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ENVIRONMENT_NAME" \
  --query properties.defaultDomain \
  --output tsv)

STATIC_IP=$(az containerapp env show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ENVIRONMENT_NAME" \
  --query properties.staticIp \
  --output tsv)

echo "Azure Container Apps shared environment ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Location                   : $LOCATION"
echo "  Log Analytics Workspace    : $WORKSPACE_NAME"
echo "  Container Apps Environment : $ENVIRONMENT_NAME"
echo "  Default Domain             : ${DEFAULT_DOMAIN:-<unavailable>}"
echo "  Static IP                  : ${STATIC_IP:-<unavailable>}"
echo "  Suggested env values:"
echo "    AZURE_LOG_ANALYTICS_WORKSPACE_NAME=$WORKSPACE_NAME"
echo "    AZURE_CONTAINER_APPS_ENVIRONMENT=$ENVIRONMENT_NAME"
echo "    AZURE_CONTAINER_APPS_DEFAULT_DOMAIN=${DEFAULT_DOMAIN:-}"
echo "    AZURE_CONTAINER_APPS_STATIC_IP=${STATIC_IP:-}"