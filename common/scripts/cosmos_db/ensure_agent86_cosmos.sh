#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
ACCOUNT_NAME=""
DATABASE_NAME="agent86"
SESSIONS_CONTAINER_NAME="sessions"
MESSAGES_CONTAINER_NAME="messages"
ARTIFACTS_CONTAINER_NAME="artifacts"
SUMMARIES_CONTAINER_NAME="summaries"
SHOW_SECRETS=false
DEFAULT_DEV_RG="rg-agent86-dev"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates or reuses the Agent 86 Cosmos DB account, SQL database, and required
containers.

Required:
  --resource-group <name>   Azure resource group containing the Cosmos account

Optional:
  --location <azure-region> Region to use when creating a new Cosmos account
  --account-name <name>     Explicit Cosmos account name to reuse/create
  --database-name <name>    SQL database name (default: $DATABASE_NAME)
  --show-secrets            Print COSMOS_KEY in the suggested env output
  --help                    Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

ensure_container() {
  local account_name="$1"
  local database_name="$2"
  local container_name="$3"
  local partition_key_path="$4"

  if az cosmosdb sql container show \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$account_name" \
    --database-name "$database_name" \
    --name "$container_name" \
    --output none >/dev/null 2>&1; then
    echo "Container '$container_name' already exists; reusing it."
    return 0
  fi

  echo "Creating container '$container_name' with partition key '$partition_key_path'..."
  az cosmosdb sql container create \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$account_name" \
    --database-name "$database_name" \
    --name "$container_name" \
    --partition-key-path "$partition_key_path" \
    --output none
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
    --show-secrets)
      SHOW_SECRETS=true
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

if [[ -z "$ACCOUNT_NAME" ]]; then
  mapfile -t discovered_accounts < <(az cosmosdb list --resource-group "$RESOURCE_GROUP" --query '[].name' --output tsv)
  existing_accounts=()
  for account in "${discovered_accounts[@]}"; do
    [[ -n "$account" ]] && existing_accounts+=("$account")
  done

  if [[ ${#existing_accounts[@]} -eq 1 ]]; then
    ACCOUNT_NAME="${existing_accounts[0]}"
    echo "Reusing discovered Cosmos account '$ACCOUNT_NAME'."
  elif [[ ${#existing_accounts[@]} -gt 1 ]]; then
    fail "Multiple Cosmos accounts found in '$RESOURCE_GROUP'. Re-run with --account-name."
  else
    if [[ "$RESOURCE_GROUP" == "$DEFAULT_DEV_RG" ]]; then
      ACCOUNT_NAME="cosmos-agent86-dev"
    else
      sanitized_rg=$(echo "$RESOURCE_GROUP" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
      ACCOUNT_NAME=$(echo "cosmos${sanitized_rg}" | cut -c1-44)
    fi
  fi
fi

if az cosmosdb show --resource-group "$RESOURCE_GROUP" --name "$ACCOUNT_NAME" --output none >/dev/null 2>&1; then
  echo "Cosmos account '$ACCOUNT_NAME' already exists; reusing it."
else
  echo "Creating Cosmos DB account '$ACCOUNT_NAME'..."
  az cosmosdb create \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --locations regionName="$LOCATION" \
    --capabilities EnableServerless \
    --default-consistency-level Session \
    --output none
fi

if az cosmosdb sql database show \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --name "$DATABASE_NAME" \
  --output none >/dev/null 2>&1; then
  echo "Cosmos SQL database '$DATABASE_NAME' already exists; reusing it."
else
  echo "Creating Cosmos SQL database '$DATABASE_NAME'..."
  az cosmosdb sql database create \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$ACCOUNT_NAME" \
    --name "$DATABASE_NAME" \
    --output none
fi

ensure_container "$ACCOUNT_NAME" "$DATABASE_NAME" "$SESSIONS_CONTAINER_NAME" "/user_id"
ensure_container "$ACCOUNT_NAME" "$DATABASE_NAME" "$MESSAGES_CONTAINER_NAME" "/session_id"
ensure_container "$ACCOUNT_NAME" "$DATABASE_NAME" "$ARTIFACTS_CONTAINER_NAME" "/session_id"
ensure_container "$ACCOUNT_NAME" "$DATABASE_NAME" "$SUMMARIES_CONTAINER_NAME" "/user_id"

COSMOS_ENDPOINT=$(az cosmosdb show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --query documentEndpoint \
  --output tsv)

[[ -n "$COSMOS_ENDPOINT" ]] || fail "Failed to resolve Cosmos endpoint"

echo "Agent 86 Cosmos resources ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Account Name               : $ACCOUNT_NAME"
echo "  Database Name              : $DATABASE_NAME"
echo "  Suggested env values:"
echo "    COSMOS_ENDPOINT=$COSMOS_ENDPOINT"
if [[ "$SHOW_SECRETS" == true ]]; then
  COSMOS_KEY=$(az cosmosdb keys list --resource-group "$RESOURCE_GROUP" --name "$ACCOUNT_NAME" --query primaryMasterKey --output tsv)
  [[ -n "$COSMOS_KEY" ]] || fail "Failed to resolve Cosmos key"
  echo "    COSMOS_KEY=$COSMOS_KEY"
else
  echo "    COSMOS_KEY=<redacted; use --show-secrets to print>"
fi
echo "    COSMOS_DATABASE_NAME=$DATABASE_NAME"
echo "    COSMOS_SESSIONS_CONTAINER_NAME=$SESSIONS_CONTAINER_NAME"
echo "    COSMOS_MESSAGES_CONTAINER_NAME=$MESSAGES_CONTAINER_NAME"
echo "    COSMOS_ARTIFACTS_CONTAINER_NAME=$ARTIFACTS_CONTAINER_NAME"
echo "    COSMOS_SUMMARIES_CONTAINER_NAME=$SUMMARIES_CONTAINER_NAME"