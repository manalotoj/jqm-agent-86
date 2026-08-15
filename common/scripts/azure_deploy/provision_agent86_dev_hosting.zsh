#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h:h}"
RESOURCE_GROUP=""
LOCATION=""
REGISTRY_NAME="acragent86dev"
WORKSPACE_NAME="law-agent86-dev"
ENVIRONMENT_NAME="acae-agent86-dev"
STATIC_WEB_APP_NAME="swa-agent86-dev"
STATIC_WEB_APP_SKU="Standard"

usage() {
  cat <<EOF
Usage: $(basename "$0") --resource-group <name> [options]

Provisions the shared Agent 86 Azure hosting resources:
  - Azure Container Registry
  - Log Analytics Workspace
  - Azure Container Apps Environment
  - Azure Static Web App

Required:
  --resource-group <name>   Azure resource group that will hold the resources

Optional:
  --location <azure-region> Resource location. Defaults to the resource group location.
  --registry-name <name>    Container registry name (default: $REGISTRY_NAME)
  --workspace-name <name>   Log Analytics workspace name (default: $WORKSPACE_NAME)
  --environment-name <name> Container Apps environment name (default: $ENVIRONMENT_NAME)
  --static-web-app-name <name> Static Web App name (default: $STATIC_WEB_APP_NAME)
  --static-web-app-sku <sku>    Static Web App SKU (default: $STATIC_WEB_APP_SKU)
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
    --registry-name)
      [[ $# -ge 2 ]] || fail "Missing value for --registry-name"
      REGISTRY_NAME="$2"
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
    --static-web-app-name)
      [[ $# -ge 2 ]] || fail "Missing value for --static-web-app-name"
      STATIC_WEB_APP_NAME="$2"
      shift 2
      ;;
    --static-web-app-sku)
      [[ $# -ge 2 ]] || fail "Missing value for --static-web-app-sku"
      STATIC_WEB_APP_SKU="$2"
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

if az group show --name "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  echo "Resource group '$RESOURCE_GROUP' already exists; reusing it."
  if [[ -z "$LOCATION" ]]; then
    LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)
  fi
else
  [[ -n "$LOCATION" ]] || fail "--location is required when creating a new resource group"
  echo "Resource group '$RESOURCE_GROUP' was not found; creating it in location '$LOCATION'..."
  az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
fi

[[ -n "$LOCATION" ]] || fail "Could not resolve Azure location"

echo "Provisioning shared Agent 86 hosting resources in resource group '$RESOURCE_GROUP' (location: $LOCATION)..."

zsh "$REPO_ROOT/common/scripts/azure_container_apps/create_container_registry.zsh" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --name "$REGISTRY_NAME"

echo ""

zsh "$REPO_ROOT/common/scripts/azure_container_apps/create_container_apps_environment.zsh" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --workspace-name "$WORKSPACE_NAME" \
  --environment-name "$ENVIRONMENT_NAME"

echo ""

zsh "$REPO_ROOT/common/scripts/azure_static_web_apps/create_static_web_app.zsh" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --name "$STATIC_WEB_APP_NAME" \
  --sku "$STATIC_WEB_APP_SKU"

echo ""
echo "Completed Agent 86 shared Azure hosting provisioning."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Container Registry         : $REGISTRY_NAME"
echo "  Log Analytics Workspace    : $WORKSPACE_NAME"
echo "  Container Apps Environment : $ENVIRONMENT_NAME"
echo "  Static Web App             : $STATIC_WEB_APP_NAME"