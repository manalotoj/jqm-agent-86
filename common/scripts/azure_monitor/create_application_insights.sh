#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
LOCATION=""
APP_INSIGHTS_NAME="appi-agent86-dev"
WORKSPACE_NAME=""
SHOW_SECRETS=false

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> [options]

Creates or reuses an Application Insights component for Agent 86.

Required:
  --resource-group <name>   Azure resource group containing the component

Optional:
  --location <azure-region> Resource location. Defaults to the resource group location.
  --name <name>             Application Insights name (default: $APP_INSIGHTS_NAME)
  --workspace-name <name>   Optional Log Analytics workspace to connect
  --show-secrets            Print the full connection string
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
      APP_INSIGHTS_NAME="$2"
      shift 2
      ;;
    --workspace-name)
      [[ $# -ge 2 ]] || fail "Missing value for --workspace-name"
      WORKSPACE_NAME="$2"
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

if az monitor app-insights component show --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" --output none >/dev/null 2>&1; then
  echo "Application Insights '$APP_INSIGHTS_NAME' already exists; reusing it."
else
  echo "Creating Application Insights '$APP_INSIGHTS_NAME'..."
  create_args=(
    --app "$APP_INSIGHTS_NAME"
    --location "$LOCATION"
    --kind web
    --application-type web
    --resource-group "$RESOURCE_GROUP"
    --output none
  )

  if [[ -n "$WORKSPACE_NAME" ]]; then
    workspace_id=$(az monitor log-analytics workspace show --resource-group "$RESOURCE_GROUP" --workspace-name "$WORKSPACE_NAME" --query id --output tsv)
    [[ -n "$workspace_id" ]] || fail "Failed to resolve Log Analytics workspace '$WORKSPACE_NAME'"
    create_args+=(--workspace "$workspace_id")
  fi

  az monitor app-insights component create "${create_args[@]}"
fi

connection_string=$(az monitor app-insights component show \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString \
  --output tsv)

[[ -n "$connection_string" ]] || fail "Failed to resolve Application Insights connection string"

echo "Application Insights ready."
echo "  Resource Group             : $RESOURCE_GROUP"
echo "  Name                       : $APP_INSIGHTS_NAME"
echo "  Suggested env values:"
if [[ "$SHOW_SECRETS" == true ]]; then
  echo "    APPLICATIONINSIGHTS_CONNECTION_STRING=$connection_string"
else
  echo "    APPLICATIONINSIGHTS_CONNECTION_STRING=<redacted; use --show-secrets to print>"
fi