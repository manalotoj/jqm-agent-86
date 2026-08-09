#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
ACCOUNT_NAME=""
DATABASE_NAME="agent86"
CONTAINER_NAME="artifacts"
PARTITION_KEY_PATH="/session_id"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> --account-name <name> [options]

Creates the Cosmos DB SQL container used for artifact metadata if it does not
already exist.

Required:
  --resource-group <name>   Azure resource group containing the Cosmos account
  --account-name <name>     Cosmos DB account name

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

if ! az cosmosdb show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --output none >/dev/null 2>&1; then
  fail "Cosmos DB account '$ACCOUNT_NAME' was not found in resource group '$RESOURCE_GROUP'"
fi

if ! az cosmosdb sql database show \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --name "$DATABASE_NAME" \
  --output none >/dev/null 2>&1; then
  fail "SQL database '$DATABASE_NAME' was not found in account '$ACCOUNT_NAME'"
fi

echo "Inspecting container '$CONTAINER_NAME' in database '$DATABASE_NAME' for account '$ACCOUNT_NAME'..."

if az cosmosdb sql container show \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --database-name "$DATABASE_NAME" \
  --name "$CONTAINER_NAME" \
  --output none >/dev/null 2>&1; then
  echo "Container already exists; no changes made."
  echo "  Resource Group : $RESOURCE_GROUP"
  echo "  Account Name   : $ACCOUNT_NAME"
  echo "  Database Name  : $DATABASE_NAME"
  echo "  Container Name : $CONTAINER_NAME"
  exit 0
fi

echo "Creating container '$CONTAINER_NAME' with partition key '$PARTITION_KEY_PATH'..."

az cosmosdb sql container create \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --database-name "$DATABASE_NAME" \
  --name "$CONTAINER_NAME" \
  --partition-key-path "$PARTITION_KEY_PATH" \
  --output jsonc

echo "Created container successfully."
echo "  Resource Group : $RESOURCE_GROUP"
echo "  Account Name   : $ACCOUNT_NAME"
echo "  Database Name  : $DATABASE_NAME"
echo "  Container Name : $CONTAINER_NAME"
echo "  Partition Key  : $PARTITION_KEY_PATH"