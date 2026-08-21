#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="$(cd -- "$SCRIPT_DIR/.." && pwd)/create_container_app.sh"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

export AZ_LOG="$TEMP_DIR/az.log"

az() {
  printf '%q ' "$@" >> "$AZ_LOG"
  printf '\n' >> "$AZ_LOG"

  case "$1 $2" in
    "acr show")
      if [[ "$*" == *"--query"*"id"* ]]; then
        printf '/subscriptions/test/resourceGroups/rg-test/providers/Microsoft.ContainerRegistry/registries/acrtest\n'
      else
        printf 'acrtest.azurecr.io\n'
      fi
      ;;
    "containerapp show")
      if [[ "$*" == *"identity.principalId"* ]]; then
        printf 'principal-id\n'
      elif [[ "$*" == *"properties.configuration.ingress.fqdn"* ]]; then
        printf 'app.example.test\n'
      elif [[ "$*" == *"properties.latestRevisionName"* ]]; then
        printf 'app--revision\n'
      fi
      ;;
    "role assignment")
      printf '1\n'
      ;;
  esac
}
export -f az

bash "$SCRIPT_UNDER_TEST" \
  --resource-group rg-test \
  --app-name aca-test \
  --environment-name acae-test \
  --image acrtest.azurecr.io/test:dev \
  --target-port 8000 \
  --ingress external \
  --registry-server acrtest.azurecr.io \
  --env APP_ENV=test \
  --secret API_KEY=secret-value

grep -F 'containerapp secret set' "$AZ_LOG" >/dev/null
grep -F -- '--secrets api-key=secret-value' "$AZ_LOG" >/dev/null
grep -F 'containerapp update' "$AZ_LOG" | grep -F -- '--replace-env-vars' >/dev/null
grep -F 'containerapp update' "$AZ_LOG" | grep -F -- 'AZURE_CONTAINER_APP_NAME=aca-test' >/dev/null
if grep -F 'containerapp update' "$AZ_LOG" | grep -Fq -- '--env-vars'; then
  echo 'update must not use --env-vars' >&2
  exit 1
fi
if grep -F 'containerapp update' "$AZ_LOG" | grep -Fq -- '--secrets'; then
  echo 'update must not use --secrets' >&2
  exit 1
fi

echo 'create_container_app existing-app update arguments: PASS'