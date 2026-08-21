#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
APP_NAME=""
ENVIRONMENT_NAME=""
IMAGE=""
TARGET_PORT=""
INGRESS="external"
REGISTRY_SERVER=""
CPU="0.5"
MEMORY="1.0Gi"
MIN_REPLICAS="0"
MAX_REPLICAS="1"
ENV_VARS=()
SECRETS=()

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> --app-name <name> --environment-name <name> --image <ref> --target-port <port> --ingress <external|internal> --registry-server <server> [options]

Creates or updates a single Azure Container App, enables system-assigned
identity, and grants AcrPull on the backing registry.

Required:
  --resource-group <name>   Azure resource group containing the Container App
  --app-name <name>         Container App name
  --environment-name <name> Container Apps environment name
  --image <ref>             Full image reference, including registry server
  --target-port <port>      Application listening port
  --ingress <mode>          Ingress mode: external or internal
  --registry-server <host>  Container registry login server

Optional:
  --cpu <value>             CPU allocation (default: $CPU)
  --memory <value>          Memory allocation (default: $MEMORY)
  --min-replicas <n>        Minimum replica count (default: $MIN_REPLICAS)
  --max-replicas <n>        Maximum replica count (default: $MAX_REPLICAS)
  --env <KEY=VALUE>         Repeatable environment variable assignment
  --secret <KEY=VALUE>      Repeatable secret assignment; values are stored as secrets and exposed as env vars
  --help                    Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

append_if_present() {
  local -n target_ref=$1
  local flag_name="$2"
  local flag_value="$3"
  if [[ -n "$flag_value" ]]; then
    target_ref+=("$flag_name" "$flag_value")
  fi
}

normalize_secret_name() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_.' '-' | tr -cd 'a-z0-9-'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group)
      [[ $# -ge 2 ]] || fail "Missing value for --resource-group"
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --app-name)
      [[ $# -ge 2 ]] || fail "Missing value for --app-name"
      APP_NAME="$2"
      shift 2
      ;;
    --environment-name)
      [[ $# -ge 2 ]] || fail "Missing value for --environment-name"
      ENVIRONMENT_NAME="$2"
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || fail "Missing value for --image"
      IMAGE="$2"
      shift 2
      ;;
    --target-port)
      [[ $# -ge 2 ]] || fail "Missing value for --target-port"
      TARGET_PORT="$2"
      shift 2
      ;;
    --ingress)
      [[ $# -ge 2 ]] || fail "Missing value for --ingress"
      INGRESS="$2"
      shift 2
      ;;
    --registry-server)
      [[ $# -ge 2 ]] || fail "Missing value for --registry-server"
      REGISTRY_SERVER="$2"
      shift 2
      ;;
    --cpu)
      [[ $# -ge 2 ]] || fail "Missing value for --cpu"
      CPU="$2"
      shift 2
      ;;
    --memory)
      [[ $# -ge 2 ]] || fail "Missing value for --memory"
      MEMORY="$2"
      shift 2
      ;;
    --min-replicas)
      [[ $# -ge 2 ]] || fail "Missing value for --min-replicas"
      MIN_REPLICAS="$2"
      shift 2
      ;;
    --max-replicas)
      [[ $# -ge 2 ]] || fail "Missing value for --max-replicas"
      MAX_REPLICAS="$2"
      shift 2
      ;;
    --env)
      [[ $# -ge 2 ]] || fail "Missing value for --env"
      ENV_VARS+=("$2")
      shift 2
      ;;
    --secret)
      [[ $# -ge 2 ]] || fail "Missing value for --secret"
      SECRETS+=("$2")
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
[[ -n "$APP_NAME" ]] || fail "--app-name is required"
[[ -n "$ENVIRONMENT_NAME" ]] || fail "--environment-name is required"
[[ -n "$IMAGE" ]] || fail "--image is required"
[[ -n "$TARGET_PORT" ]] || fail "--target-port is required"
[[ -n "$REGISTRY_SERVER" ]] || fail "--registry-server is required"
[[ "$INGRESS" == "external" || "$INGRESS" == "internal" ]] || fail "--ingress must be 'external' or 'internal'"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az group show --name "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  fail "Resource group '$RESOURCE_GROUP' was not found"
fi

if ! az containerapp env show --resource-group "$RESOURCE_GROUP" --name "$ENVIRONMENT_NAME" --output none >/dev/null 2>&1; then
  fail "Container Apps environment '$ENVIRONMENT_NAME' was not found in resource group '$RESOURCE_GROUP'"
fi

REGISTRY_NAME=${REGISTRY_SERVER%%.*}
if ! az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --output none >/dev/null 2>&1; then
  fail "Container registry '$REGISTRY_NAME' was not found in resource group '$RESOURCE_GROUP'"
fi

ACR_RESOURCE_ID=$(az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --query id --output tsv)
[[ -n "$ACR_RESOURCE_ID" ]] || fail "Failed to resolve container registry resource ID"

SECRET_ASSIGNMENTS=()
ENV_ASSIGNMENTS=("AZURE_CONTAINER_APP_NAME=$APP_NAME")
for env_var in "${ENV_VARS[@]}"; do
  [[ "$env_var" == *=* ]] || fail "--env values must use KEY=VALUE format"
  ENV_ASSIGNMENTS+=("$env_var")
done

for secret in "${SECRETS[@]}"; do
  [[ "$secret" == *=* ]] || fail "--secret values must use KEY=VALUE format"
  key=${secret%%=*}
  value=${secret#*=}
  [[ -n "$key" ]] || fail "Secret key cannot be empty"
  secret_name=$(normalize_secret_name "$key")
  [[ -n "$secret_name" ]] || fail "Failed to normalize secret key '$key'"
  SECRET_ASSIGNMENTS+=("$secret_name=$value")
  ENV_ASSIGNMENTS+=("$key=secretref:$secret_name")
done

CREATE_ARGS=(
  --name "$APP_NAME"
  --resource-group "$RESOURCE_GROUP"
  --environment "$ENVIRONMENT_NAME"
  --image "$IMAGE"
  --target-port "$TARGET_PORT"
  --ingress "$INGRESS"
  --registry-server "$REGISTRY_SERVER"
  --cpu "$CPU"
  --memory "$MEMORY"
  --min-replicas "$MIN_REPLICAS"
  --max-replicas "$MAX_REPLICAS"
  --system-assigned
  --output none
)

# Environment, ingress, registry, and identity are creation-time configuration.
# Passing those create-only arguments to `az containerapp update` causes the CLI
# extension to submit an invalid update payload for an existing app.
UPDATE_ARGS=(
  --name "$APP_NAME"
  --resource-group "$RESOURCE_GROUP"
  --image "$IMAGE"
  --cpu "$CPU"
  --memory "$MEMORY"
  --min-replicas "$MIN_REPLICAS"
  --max-replicas "$MAX_REPLICAS"
  --output none
)

if (( ${#ENV_ASSIGNMENTS[@]} > 0 )); then
  CREATE_ARGS+=(--env-vars)
  CREATE_ARGS+=("${ENV_ASSIGNMENTS[@]}")
  UPDATE_ARGS+=(--replace-env-vars)
  UPDATE_ARGS+=("${ENV_ASSIGNMENTS[@]}")
fi

if (( ${#SECRET_ASSIGNMENTS[@]} > 0 )); then
  CREATE_ARGS+=(--secrets)
  CREATE_ARGS+=("${SECRET_ASSIGNMENTS[@]}")
fi

echo "Preparing Azure Container App '$APP_NAME'..."

if az containerapp show --resource-group "$RESOURCE_GROUP" --name "$APP_NAME" --output none >/dev/null 2>&1; then
  echo "Container App already exists; updating it."
  if (( ${#SECRET_ASSIGNMENTS[@]} > 0 )); then
    az containerapp secret set \
      --name "$APP_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --secrets "${SECRET_ASSIGNMENTS[@]}" \
      --output none
  fi
  az containerapp update "${UPDATE_ARGS[@]}"
else
  echo "Creating Container App '$APP_NAME'..."
  az containerapp create "${CREATE_ARGS[@]}"
fi

PRINCIPAL_ID=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --query identity.principalId \
  --output tsv)

[[ -n "$PRINCIPAL_ID" ]] || fail "Failed to resolve managed identity principal ID for '$APP_NAME'"

ROLE_COUNT=$(az role assignment list \
  --assignee-object-id "$PRINCIPAL_ID" \
  --scope "$ACR_RESOURCE_ID" \
  --query "[?roleDefinitionName=='AcrPull'] | length(@)" \
  --output tsv)

if [[ "${ROLE_COUNT:-0}" == "0" ]]; then
  echo "Granting AcrPull on '$REGISTRY_NAME' to Container App managed identity..."
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role AcrPull \
    --scope "$ACR_RESOURCE_ID" \
    --output none
fi

FQDN=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

LATEST_REVISION=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --query properties.latestRevisionName \
  --output tsv)

echo "Azure Container App ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Container App              : $APP_NAME"
echo "  Environment                : $ENVIRONMENT_NAME"
echo "  Image                      : $IMAGE"
echo "  Ingress                    : $INGRESS"
echo "  Target Port                : $TARGET_PORT"
echo "  Latest Revision            : ${LATEST_REVISION:-<unavailable>}"
echo "  FQDN                       : ${FQDN:-<unavailable>}"
echo "  Suggested env values:"
echo "    AZURE_CONTAINER_APP_NAME=$APP_NAME"
echo "    AZURE_CONTAINER_APP_FQDN=${FQDN:-}"
if [[ -n "${FQDN:-}" && "$INGRESS" == "external" ]]; then
  echo "    AZURE_CONTAINER_APP_URL=https://$FQDN"
fi