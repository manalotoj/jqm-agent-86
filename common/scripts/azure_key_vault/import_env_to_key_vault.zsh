#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
KEY_VAULT_NAME=""
ENV_FILE=""
DRY_RUN=false

typeset -A SECRET_NAME_MAP
SECRET_NAME_MAP=(
  COSMOS_KEY cosmos-key
  AZURE_BLOB_CONNECTION_STRING azure-blob-connection-string
  FOUNDRY_OPENAI_API_KEY foundry-openai-api-key
  TAVILY_API_KEY tavily-api-key
  BRAVE_SEARCH_API_KEY brave-search-api-key
  APPLICATIONINSIGHTS_CONNECTION_STRING applicationinsights-connection-string
  AZURE_STATIC_WEB_APP_DEPLOYMENT_TOKEN azure-static-web-app-deployment-token
  E2E_ENTRA_CLIENT_SECRET e2e-entra-client-secret
  ENTRA_UI_CLIENT_SECRET entra-ui-client-secret
)

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --key-vault-name <name> --env-file <path> [options]

Imports an explicit allowlist of secret values from an env file into Azure Key
Vault.

Required:
  --key-vault-name <name>    Azure Key Vault name
  --env-file <path>          Env file to parse

Optional:
  --dry-run                  Print what would be imported without writing
  --help                     Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

trim_quotes() {
  local value="$1"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value#\"}"
    value="${value%\"}"
  elif [[ "$value" == \'.*\' ]]; then
    value="${value#\'}"
    value="${value%\'}"
  fi
  echo "$value"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key-vault-name)
      [[ $# -ge 2 ]] || fail "Missing value for --key-vault-name"
      KEY_VAULT_NAME="$2"
      shift 2
      ;;
    --env-file)
      [[ $# -ge 2 ]] || fail "Missing value for --env-file"
      ENV_FILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
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

[[ -n "$KEY_VAULT_NAME" ]] || fail "--key-vault-name is required"
[[ -n "$ENV_FILE" ]] || fail "--env-file is required"
[[ -f "$ENV_FILE" ]] || fail "Env file '$ENV_FILE' was not found"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."
az keyvault show --name "$KEY_VAULT_NAME" --output none >/dev/null 2>&1 || fail "Key Vault '$KEY_VAULT_NAME' was not found"

import_count=0
while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
  line="${raw_line#${raw_line%%[![:space:]]*}}"
  [[ -n "$line" ]] || continue
  [[ "$line" == \#* ]] && continue
  [[ "$line" == *=* ]] || continue

  key="${line%%=*}"
  value="${line#*=}"
  key="${key%%[[:space:]]*}"
  [[ -n "${SECRET_NAME_MAP[$key]:-}" ]] || continue
  value=$(trim_quotes "$value")
  [[ -n "$value" ]] || continue

  secret_name="${SECRET_NAME_MAP[$key]}"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] Would import $key as secret '$secret_name'"
  else
    echo "Importing $key as secret '$secret_name'..."
    az keyvault secret set \
      --vault-name "$KEY_VAULT_NAME" \
      --name "$secret_name" \
      --value "$value" \
      --output none
  fi
  import_count=$((import_count + 1))
done < "$ENV_FILE"

echo "Processed $import_count secret value(s) from '$ENV_FILE'."