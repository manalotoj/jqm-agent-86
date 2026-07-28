#!/usr/bin/env zsh
set -euo pipefail

# -----------------------------
# Reusable variables
# -----------------------------
SUBSCRIPTION_ID=""                  # optional: set if you use multiple subscriptions
RG="rg-agent86-dev"
LOCATION="westus"
COSMOS_ACCOUNT="agent86$RANDOM$RANDOM"
COSMOS_DB_NAME="agent86"
COSMOS_CONTAINER="sessions"
COSMOS_PARTITION_KEY="/user_id"

# -----------------------------
# Login / subscription
# -----------------------------
az account show >/dev/null 2>&1 || az login

if [[ -n "${SUBSCRIPTION_ID}" ]]; then
  az account set --subscription "$SUBSCRIPTION_ID"
fi

# -----------------------------
# Resource group
# -----------------------------
az group create \
  --name "$RG" \
  --location "$LOCATION"

# -----------------------------
# Cosmos DB account (NoSQL, serverless)
# -----------------------------
az cosmosdb create \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RG" \
  --locations regionName="$LOCATION" \
  --capabilities EnableServerless

# -----------------------------
# SQL database
# -----------------------------
az cosmosdb sql database create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RG" \
  --name "$COSMOS_DB_NAME"

# -----------------------------
# SQL container
# -----------------------------
az cosmosdb sql container create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RG" \
  --database-name "$COSMOS_DB_NAME" \
  --name "$COSMOS_CONTAINER" \
  --partition-key-path "$COSMOS_PARTITION_KEY"

# -----------------------------
# Fetch endpoint + key for local app config
# -----------------------------
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RG" \
  --query documentEndpoint \
  --output tsv)

COSMOS_KEY=$(az cosmosdb keys list \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RG" \
  --type keys \
  --query primaryMasterKey \
  --output tsv)

# -----------------------------
# Output
# -----------------------------
echo ""
echo "Created Azure Cosmos DB resources:"
echo "  Resource Group : $RG"
echo "  Location       : $LOCATION"
echo "  Account Name   : $COSMOS_ACCOUNT"
echo "  Database Name  : $COSMOS_DB_NAME"
echo "  Container Name : $COSMOS_CONTAINER"
echo "  Partition Key  : $COSMOS_PARTITION_KEY"
echo ""
echo "Use these in your .env:"
echo "COSMOS_ENDPOINT=$COSMOS_ENDPOINT"
echo "COSMOS_KEY=$COSMOS_KEY"
echo "COSMOS_DATABASE_NAME=$COSMOS_DB_NAME"
echo "COSMOS_SESSIONS_CONTAINER_NAME=$COSMOS_CONTAINER"

#
# create messages container
#
az cosmosdb sql container create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RG" \
  --database-name "$COSMOS_DB_NAME" \
  --name messages \
  --partition-key-path "/session_id"