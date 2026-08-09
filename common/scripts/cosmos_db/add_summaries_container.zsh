#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
ACCOUNT_NAME=""
DATABASE_NAME="agent86"
CONTAINER_NAME="summaries"
PARTITION_KEY_PATH="/user_id"
ALL_IN_DEV_RG=0
DEFAULT_DEV_RG="rg-agent86-dev"

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME --resource-group <name> --account-name <name> [options]
  $SCRIPT_NAME --all-dev-accounts [options]

Creates the Cosmos DB SQL container used for session summaries if it does not
already exist.

Required (choose one mode):
  --resource-group <name>   Azure resource group containing the Cosmos account
  --account-name <name>     Cosmos DB account name
  --all-dev-accounts        Apply to all Cosmos DB accounts in ${DEFAULT_DEV_RG}

Optional:
  --database-name <name>    SQL database name (default: $DATABASE_NAME)
  --container-name <name>   Container name (default: $CONTAINER_NAME)
  --help                    Show this help text

The container is created with partition key path: $PARTITION_KEY_PATH
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

ensure_container() {
  local resource_group="$1"
  local account_name="$2"

  if ! az cosmosdb show \
    --resource-group "$resource_group" \
    --name "$account_name" \
    --output none >/dev/null 2>&1; then
    fail "Cosmos DB account '$account_name' was not found in resource group '$resource_group'"
  fi

  if ! az cosmosdb sql database show \
    --resource-group "$resource_group" \
    --account-name "$account_name" \
    --name "$DATABASE_NAME" \
    --output none >/dev/null 2>&1; then
    fail "SQL database '$DATABASE_NAME' was not found in account '$account_name'"
  fi

  echo "Inspecting container '$CONTAINER_NAME' in database '$DATABASE_NAME' for account '$account_name'..."

  if az cosmosdb sql container show \
    --resource-group "$resource_group" \
    --account-name "$account_name" \
    --database-name "$DATABASE_NAME" \
    --name "$CONTAINER_NAME" \
    --output none >/dev/null 2>&1; then
    echo "Container already exists; no changes made."
    echo "  Resource Group : $resource_group"
    echo "  Account Name   : $account_name"
    echo "  Database Name  : $DATABASE_NAME"
    echo "  Container Name : $CONTAINER_NAME"
    return 0
  fi

  echo "Creating container '$CONTAINER_NAME' with partition key '$PARTITION_KEY_PATH'..."

  az cosmosdb sql container create \
    --resource-group "$resource_group" \
    --account-name "$account_name" \
    --database-name "$DATABASE_NAME" \
    --name "$CONTAINER_NAME" \
    --partition-key-path "$PARTITION_KEY_PATH" \
    --output jsonc

  echo "Created container successfully."
  echo "  Resource Group : $resource_group"
  echo "  Account Name   : $account_name"
  echo "  Database Name  : $DATABASE_NAME"
  echo "  Container Name : $CONTAINER_NAME"
  echo "  Partition Key  : $PARTITION_KEY_PATH"
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
    --database-name)
      [[ $# -ge 2 ]] || fail "Missing value for --database-name"
      DATABASE_NAME="$2"
      shift 2
      ;;
    --container-name)
      [[ $# -ge 2 ]] || fail "Missing value for --container-name"
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --all-dev-accounts)
      ALL_IN_DEV_RG=1
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

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if (( ALL_IN_DEV_RG == 1 )); then
  [[ -z "$RESOURCE_GROUP" ]] || fail "Do not combine --all-dev-accounts with --resource-group"
  [[ -z "$ACCOUNT_NAME" ]] || fail "Do not combine --all-dev-accounts with --account-name"

  cosmos_accounts=(
    "${(@f)$(az cosmosdb list \
      --resource-group "$DEFAULT_DEV_RG" \
      --query "[].name" \
      --output tsv)}"
  )

  (( ${#cosmos_accounts[@]} > 0 )) || fail "No Cosmos DB accounts found in resource group '$DEFAULT_DEV_RG'"

  for account in "${cosmos_accounts[@]}"; do
    ensure_container "$DEFAULT_DEV_RG" "$account"
  done

  exit 0
fi

[[ -n "$RESOURCE_GROUP" ]] || fail "--resource-group is required unless --all-dev-accounts is used"
[[ -n "$ACCOUNT_NAME" ]] || fail "--account-name is required unless --all-dev-accounts is used"

ensure_container "$RESOURCE_GROUP" "$ACCOUNT_NAME"