#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
CONTAINER_NAME="agent86-artifacts"
DERIVED_CONTAINER_NAME="agent86-artifact-derived"
DERIVED_RETENTION_DAYS=30
NAME_PREFIX="agent86"
SKU="Standard_LRS"
ENVIRONMENTS_CSV="dev,e2e"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates Azure Blob Storage resources for Agent 86 artifacts. By default this
creates one storage account for dev and one for e2e, then creates the artifact
blob container in each account.

Required:
  --resource-group <name>   Azure resource group that will hold the storage accounts

Optional:
  --location <azure-region> Storage account location. Defaults to the resource group location.
  --container-name <name>   Blob container name (default: $CONTAINER_NAME)
  --derived-retention-days <days>
                            Delete derived artifact blobs after this many days
                            (default: $DERIVED_RETENTION_DAYS)
  --name-prefix <prefix>    Prefix for generated storage account names (default: $NAME_PREFIX)
  --sku <sku>               Storage account SKU (default: $SKU)
  --environments <csv>      Comma-separated environment list (default: $ENVIRONMENTS_CSV)
  --help                    Show this help text

Generated account names are deterministic per subscription and environment so
the script can be re-run safely.

The resulting storage account and blob container names are printed after
provisioning completes.
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

trim() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  echo "$value"
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
    --container-name)
      [[ $# -ge 2 ]] || fail "Missing value for --container-name"
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --derived-retention-days)
      [[ $# -ge 2 ]] || fail "Missing value for --derived-retention-days"
      DERIVED_RETENTION_DAYS="$2"
      shift 2
      ;;
    --name-prefix)
      [[ $# -ge 2 ]] || fail "Missing value for --name-prefix"
      NAME_PREFIX="$2"
      shift 2
      ;;
    --sku)
      [[ $# -ge 2 ]] || fail "Missing value for --sku"
      SKU="$2"
      shift 2
      ;;
    --environments)
      [[ $# -ge 2 ]] || fail "Missing value for --environments"
      ENVIRONMENTS_CSV="$2"
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
[[ "$DERIVED_RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || fail "--derived-retention-days must be a positive integer"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az group show --name "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  fail "Resource group '$RESOURCE_GROUP' was not found"
fi

if [[ -z "$LOCATION" ]]; then
  LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)
fi

[[ -n "$LOCATION" ]] || fail "Could not resolve Azure location"

SUBSCRIPTION_ID=$(az account show --query id --output tsv)
SUBSCRIPTION_SUFFIX=$(echo "$SUBSCRIPTION_ID" | tr -d '-' | cut -c1-8)

if [[ -z "$SUBSCRIPTION_SUFFIX" ]]; then
  fail "Could not derive a subscription-specific storage account suffix"
fi

ENVIRONMENTS=()
IFS=',' read -r -a raw_environments <<< "$ENVIRONMENTS_CSV"
for raw_environment in "${raw_environments[@]}"; do
  environment=$(trim "$raw_environment")
  [[ -n "$environment" ]] || continue
  sanitized_environment=$(echo "$environment" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
  [[ -n "$sanitized_environment" ]] || fail "Environment '$environment' becomes empty after sanitization"
  ENVIRONMENTS+=("$sanitized_environment")
done

(( ${#ENVIRONMENTS[@]} > 0 )) || fail "At least one environment must be provided"

build_account_name() {
  local environment="$1"
  local prefix
  local max_prefix_length

  prefix=$(echo "$NAME_PREFIX" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
  [[ -n "$prefix" ]] || fail "--name-prefix must contain at least one alphanumeric character"

  max_prefix_length=$((24 - ${#environment} - ${#SUBSCRIPTION_SUFFIX}))
  (( max_prefix_length >= 3 )) || fail "Generated storage account name would be too long; use a shorter --name-prefix"
  prefix=$(echo "$prefix" | cut -c1-"$max_prefix_length")

  echo "${prefix}${environment}${SUBSCRIPTION_SUFFIX}"
}

create_container_if_missing() {
  local account_name="$1"
  local account_key="$2"
  local container_name="$3"

  if az storage container exists \
    --account-name "$account_name" \
    --account-key "$account_key" \
    --name "$container_name" \
    --query exists \
    --output tsv | grep -qi '^true$'; then
    echo "Container '$container_name' already exists in storage account '$account_name'."
    return 0
  fi

  echo "Creating blob container '$container_name' in storage account '$account_name'..."

  az storage container create \
    --account-name "$account_name" \
    --account-key "$account_key" \
    --name "$container_name" \
    --public-access off \
    --output none
}

echo "Preparing Azure Blob Storage resources in resource group '$RESOURCE_GROUP' (location: $LOCATION)..."
echo ""

RESULTING_RESOURCES=()

for environment in "${ENVIRONMENTS[@]}"; do
  account_name=$(build_account_name "$environment")

  echo "[$environment] Target storage account: $account_name"

  if az storage account show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$account_name" \
    --output none >/dev/null 2>&1; then
    echo "[$environment] Storage account already exists; reusing it."
  else
    availability=$(az storage account check-name --name "$account_name" --query nameAvailable --output tsv)
    if [[ "$availability" != "true" ]]; then
      fail "Storage account name '$account_name' is unavailable globally. Re-run with a different --name-prefix."
    fi

    echo "[$environment] Creating storage account..."
    az storage account create \
      --resource-group "$RESOURCE_GROUP" \
      --name "$account_name" \
      --location "$LOCATION" \
      --sku "$SKU" \
      --kind StorageV2 \
      --allow-blob-public-access false \
      --min-tls-version TLS1_2 \
      --https-only true \
      --output none
  fi

  account_key=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$account_name" \
    --query '[0].value' \
    --output tsv)

  [[ -n "$account_key" ]] || fail "Failed to retrieve an account key for '$account_name'"

  create_container_if_missing "$account_name" "$account_key" "$CONTAINER_NAME"
  create_container_if_missing "$account_name" "$account_key" "$DERIVED_CONTAINER_NAME"
  bash "$(dirname "$0")/ensure_derived_artifact_lifecycle_policy.sh" \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$account_name" \
    --retention-days "$DERIVED_RETENTION_DAYS"

  echo "[$environment] Ready."
  echo "  Resource Group             : $RESOURCE_GROUP"
  echo "  Location                   : $LOCATION"
  echo "  Storage Account            : $account_name"
  echo "  Blob Container             : $CONTAINER_NAME"
  echo "  Derived Blob Container     : $DERIVED_CONTAINER_NAME"
  echo "  Derived Blob Retention     : $DERIVED_RETENTION_DAYS days"
  echo ""

  RESULTING_RESOURCES+=("$environment|$account_name|$CONTAINER_NAME")
done

echo "Completed Azure Blob Storage provisioning."
echo "Resulting resources:"
for resource in "${RESULTING_RESOURCES[@]}"; do
  IFS='|' read -r environment account_name container_name <<< "$resource"
  echo "  Environment '$environment': storage account '$account_name', blob container '$container_name'"
done