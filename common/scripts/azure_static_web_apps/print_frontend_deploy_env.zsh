#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
API_URL=""
REDIRECT_URI=""
TENANT_ID=""
CLIENT_ID=""
API_SCOPE=""

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --api-url <https-url> --redirect-uri <https-url> --tenant-id <id> --client-id <id> --api-scope <scope>

Prints the frontend environment values needed for Azure Static Web App builds.

Required:
  --api-url <https-url>     Public HTTPS base URL for the main API
  --redirect-uri <https-url> Redirect URI for the Static Web App frontend
  --tenant-id <id>          Microsoft Entra tenant ID
  --client-id <id>          Frontend SPA client ID
  --api-scope <scope>       API access scope requested by the frontend
  --help                    Show this help text
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url)
      [[ $# -ge 2 ]] || fail "Missing value for --api-url"
      API_URL="$2"
      shift 2
      ;;
    --redirect-uri)
      [[ $# -ge 2 ]] || fail "Missing value for --redirect-uri"
      REDIRECT_URI="$2"
      shift 2
      ;;
    --tenant-id)
      [[ $# -ge 2 ]] || fail "Missing value for --tenant-id"
      TENANT_ID="$2"
      shift 2
      ;;
    --client-id)
      [[ $# -ge 2 ]] || fail "Missing value for --client-id"
      CLIENT_ID="$2"
      shift 2
      ;;
    --api-scope)
      [[ $# -ge 2 ]] || fail "Missing value for --api-scope"
      API_SCOPE="$2"
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

[[ -n "$API_URL" ]] || fail "--api-url is required"
[[ -n "$REDIRECT_URI" ]] || fail "--redirect-uri is required"
[[ -n "$TENANT_ID" ]] || fail "--tenant-id is required"
[[ -n "$CLIENT_ID" ]] || fail "--client-id is required"
[[ -n "$API_SCOPE" ]] || fail "--api-scope is required"

echo "VITE_ENTRA_CLIENT_ID=$CLIENT_ID"
echo "VITE_ENTRA_TENANT_ID=$TENANT_ID"
echo "VITE_REDIRECT_URI=$REDIRECT_URI"
echo "VITE_API_SCOPE=$API_SCOPE"
echo "VITE_API_BASE_URL=$API_URL"