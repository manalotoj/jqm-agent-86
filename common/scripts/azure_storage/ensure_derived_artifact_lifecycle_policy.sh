#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESOURCE_GROUP=""
ACCOUNT_NAME=""
RETENTION_DAYS=30

usage() {
  cat <<EOF
Usage: $(basename "$0") --resource-group <name> --account-name <name> [options]

Idempotently configures a lifecycle rule which deletes only block blobs in the
private agent86-artifact-derived container. Existing unrelated lifecycle rules
on the storage account are preserved.

Required:
  --resource-group <name>  Resource group containing the storage account
  --account-name <name>    Storage account to configure

Optional:
  --retention-days <days>  Delete after this many days (default: $RETENTION_DAYS)
  --help                   Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group) RESOURCE_GROUP="${2:-}"; shift 2 ;;
    --account-name) ACCOUNT_NAME="${2:-}"; shift 2 ;;
    --retention-days) RETENTION_DAYS="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

[[ -n "$RESOURCE_GROUP" ]] || fail "--resource-group is required"
[[ -n "$ACCOUNT_NAME" ]] || fail "--account-name is required"
[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || fail "--retention-days must be a positive integer"
command -v az >/dev/null || fail "Azure CLI is required"

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
existing_policy="$temporary_directory/existing-policy.json"
updated_policy="$temporary_directory/updated-policy.json"

# An account without a policy returns a non-zero status. Start from a valid,
# empty document in that expected case; do not discard an existing policy.
policy_error="$temporary_directory/management-policy-show.err"
if ! az storage account management-policy show \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --output json >"$existing_policy" 2>"$policy_error"; then
  if grep -Eqi 'ManagementPolicyNotFound|ResourceNotFound|could not be found' "$policy_error"; then
    printf '{"policy":{"rules":[]}}\n' >"$existing_policy"
  else
    cat "$policy_error" >&2
    fail "Could not read the existing lifecycle policy; refusing to risk unrelated rules"
  fi
fi

python3 "$SCRIPT_DIR/ensure_derived_artifact_lifecycle_policy.py" \
  --input "$existing_policy" \
  --output "$updated_policy" \
  --days "$RETENTION_DAYS"

az storage account management-policy update \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --policy "@$updated_policy" \
  --output none

az storage account management-policy show \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --query "policy.rules[?name=='delete-agent86-derived-artifacts'].{enabled:enabled,prefix:definition.filters.prefixMatch,days:definition.actions.baseBlob.delete.daysAfterModificationGreaterThan}" \
  --output json