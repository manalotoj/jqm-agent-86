#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
KEY_VAULT_NAME=""
NAME_PREFIX="kv-agent86-dev"
ENABLE_RBAC=true

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates or reuses an Azure Key Vault for Agent 86.

Required:
  --resource-group <name>   Azure resource group containing the Key Vault

Optional:
  --location <azure-region> Resource location. Defaults to the resource group location.
  --name <name>             Explicit Key Vault name to reuse/create
  --name-prefix <prefix>    Prefix used for generated names (default: $NAME_PREFIX)
  --disable-rbac            Create the vault without RBAC authorization
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
      KEY_VAULT_NAME="$2"
      shift 2
      ;;
    --name-prefix)
      [[ $# -ge 2 ]] || fail "Missing value for --name-prefix"
      NAME_PREFIX="$2"
      shift 2
      ;;
    --disable-rbac)
      ENABLE_RBAC=false
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

if [[ -z "$KEY_VAULT_NAME" ]]; then
  mapfile -t discovered_vaults < <(az keyvault list --resource-group "$RESOURCE_GROUP" --query '[].name' --output tsv)
  existing_vaults=()
  for vault in "${discovered_vaults[@]}"; do
    [[ -n "$vault" ]] && existing_vaults+=("$vault")
  done
  if [[ ${#existing_vaults[@]} -eq 1 ]]; then
    KEY_VAULT_NAME="${existing_vaults[0]}"
    echo "Reusing discovered Key Vault '$KEY_VAULT_NAME'."
  elif [[ ${#existing_vaults[@]} -gt 1 ]]; then
    fail "Multiple Key Vaults found in '$RESOURCE_GROUP'. Re-run with --name."
  else
    subscription_id=$(az account show --query id --output tsv)
    suffix=$(echo "$subscription_id" | tr -d '-' | cut -c1-6)
    prefix=$(echo "$NAME_PREFIX" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')
    KEY_VAULT_NAME=$(echo "${prefix}-${suffix}" | cut -c1-24)
  fi
fi

if az keyvault show --resource-group "$RESOURCE_GROUP" --name "$KEY_VAULT_NAME" --output none >/dev/null 2>&1; then
  echo "Key Vault '$KEY_VAULT_NAME' already exists; reusing it."
else
  echo "Creating Key Vault '$KEY_VAULT_NAME'..."
  create_args=(
    --resource-group "$RESOURCE_GROUP"
    --name "$KEY_VAULT_NAME"
    --location "$LOCATION"
    --output none
  )
  if [[ "$ENABLE_RBAC" == true ]]; then
    create_args+=(--enable-rbac-authorization true)
  fi
  az keyvault create "${create_args[@]}"
fi

vault_uri=$(az keyvault show --resource-group "$RESOURCE_GROUP" --name "$KEY_VAULT_NAME" --query properties.vaultUri --output tsv)
[[ -n "$vault_uri" ]] || fail "Failed to resolve Key Vault URI"

echo "Key Vault ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Name                       : $KEY_VAULT_NAME"
echo "  Suggested env values:"
echo "    AZURE_KEY_VAULT_NAME=$KEY_VAULT_NAME"
echo "    AZURE_KEY_VAULT_URI=$vault_uri"