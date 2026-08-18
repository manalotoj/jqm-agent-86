#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
REGISTRY_NAME="acragent86dev"
SKU="Basic"
SHOW_CREDENTIALS=false

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates or reuses the Agent 86 Azure Container Registry in the target resource
group.

Required:
  --resource-group <name>   Azure resource group that will hold the registry

Optional:
  --location <azure-region> Registry location. Defaults to the resource group location.
  --name <name>             Registry name (default: $REGISTRY_NAME)
  --sku <sku>               Registry SKU (default: $SKU)
  --show-credentials        Print admin username/password after provisioning
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
      REGISTRY_NAME="$2"
      shift 2
      ;;
    --sku)
      [[ $# -ge 2 ]] || fail "Missing value for --sku"
      SKU="$2"
      shift 2
      ;;
    --show-credentials)
      SHOW_CREDENTIALS=true
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
[[ "$REGISTRY_NAME" =~ ^[a-zA-Z0-9]+$ ]] || fail "Registry name must be alphanumeric only"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az group show --name "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  fail "Resource group '$RESOURCE_GROUP' was not found"
fi

if [[ -z "$LOCATION" ]]; then
  LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)
fi

[[ -n "$LOCATION" ]] || fail "Could not resolve Azure location"

echo "Preparing Azure Container Registry '$REGISTRY_NAME' in resource group '$RESOURCE_GROUP' (location: $LOCATION)..."

if az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --output none >/dev/null 2>&1; then
  echo "Container registry already exists; reusing it."
else
  availability=$(az acr check-name --name "$REGISTRY_NAME" --query nameAvailable --output tsv)
  if [[ "$availability" != "true" ]]; then
    fail "Container registry name '$REGISTRY_NAME' is unavailable globally. Re-run with --name."
  fi

  az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$REGISTRY_NAME" \
    --location "$LOCATION" \
    --sku "$SKU" \
    --admin-enabled true \
    --output none
fi

LOGIN_SERVER=$(az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --query loginServer --output tsv)
RESOURCE_ID=$(az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --query id --output tsv)

[[ -n "$LOGIN_SERVER" ]] || fail "Failed to resolve registry login server"
[[ -n "$RESOURCE_ID" ]] || fail "Failed to resolve registry resource ID"

echo "Azure Container Registry ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Location                   : $LOCATION"
echo "  Registry Name              : $REGISTRY_NAME"
echo "  Login Server               : $LOGIN_SERVER"
echo "  Resource ID                : $RESOURCE_ID"
echo "  Suggested env values:"
echo "    AZURE_CONTAINER_REGISTRY_NAME=$REGISTRY_NAME"
echo "    AZURE_CONTAINER_REGISTRY_LOGIN_SERVER=$LOGIN_SERVER"
echo "    AZURE_CONTAINER_REGISTRY_RESOURCE_ID=$RESOURCE_ID"

if [[ "$SHOW_CREDENTIALS" == true ]]; then
  USERNAME=$(az acr credential show --name "$REGISTRY_NAME" --query username --output tsv)
  PASSWORD=$(az acr credential show --name "$REGISTRY_NAME" --query 'passwords[0].value' --output tsv)
  [[ -n "$USERNAME" ]] || fail "Failed to resolve registry username"
  [[ -n "$PASSWORD" ]] || fail "Failed to resolve registry password"
  echo "    AZURE_CONTAINER_REGISTRY_USERNAME=$USERNAME"
  echo "    AZURE_CONTAINER_REGISTRY_PASSWORD=$PASSWORD"
fi