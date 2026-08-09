#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
ACCOUNT_NAME=""
CONTAINER_NAME="agent86-artifacts"
REDACT_KEYS=true

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> --account-name <name> [options]

Prints the Azure Blob Storage environment variables needed by the backend for a
single artifact storage account. By default the account key is redacted so the
output is safer to paste into docs, tickets, or reviews.

Required:
  --resource-group <name>   Azure resource group containing the storage account
  --account-name <name>     Azure Storage account name

Optional:
  --container-name <name>   Blob container name (default: $CONTAINER_NAME)
  --show-secrets            Print the full connection string without redaction
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
    --account-name)
      [[ $# -ge 2 ]] || fail "Missing value for --account-name"
      ACCOUNT_NAME="$2"
      shift 2
      ;;
    --container-name)
      [[ $# -ge 2 ]] || fail "Missing value for --container-name"
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --show-secrets)
      REDACT_KEYS=false
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
[[ -n "$ACCOUNT_NAME" ]] || fail "--account-name is required"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az storage account show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --output none >/dev/null 2>&1; then
  fail "Storage account '$ACCOUNT_NAME' was not found in resource group '$RESOURCE_GROUP'"
fi

connection_string=$(az storage account show-connection-string \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --query connectionString \
  --output tsv)

[[ -n "$connection_string" ]] || fail "Failed to resolve the connection string for '$ACCOUNT_NAME'"

if [[ "$REDACT_KEYS" == true ]]; then
  connection_string=$(echo "$connection_string" | sed 's/AccountKey=[^;]*/AccountKey=<redacted>/')
fi

echo "AZURE_BLOB_CONNECTION_STRING=$connection_string"
echo "AZURE_BLOB_CONTAINER_NAME=$CONTAINER_NAME"