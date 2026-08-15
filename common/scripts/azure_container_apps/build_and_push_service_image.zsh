#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
RESOURCE_GROUP=""
REGISTRY_NAME=""
IMAGE_NAME=""
IMAGE_TAG=""
BUILD_CONTEXT=""
DOCKERFILE_PATH=""

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME --resource-group <name> --registry-name <name> --image-name <name> --image-tag <tag> --context <path> --dockerfile <path>

Builds a service image with Azure Container Registry Tasks and pushes it to the
target registry.

Required:
  --resource-group <name>   Azure resource group containing the registry
  --registry-name <name>    Azure Container Registry name
  --image-name <name>       Repository/image name to publish
  --image-tag <tag>         Image tag to publish
  --context <path>          Build context directory
  --dockerfile <path>       Dockerfile path, absolute or relative to the context
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
    --registry-name)
      [[ $# -ge 2 ]] || fail "Missing value for --registry-name"
      REGISTRY_NAME="$2"
      shift 2
      ;;
    --image-name)
      [[ $# -ge 2 ]] || fail "Missing value for --image-name"
      IMAGE_NAME="$2"
      shift 2
      ;;
    --image-tag)
      [[ $# -ge 2 ]] || fail "Missing value for --image-tag"
      IMAGE_TAG="$2"
      shift 2
      ;;
    --context)
      [[ $# -ge 2 ]] || fail "Missing value for --context"
      BUILD_CONTEXT="$2"
      shift 2
      ;;
    --dockerfile)
      [[ $# -ge 2 ]] || fail "Missing value for --dockerfile"
      DOCKERFILE_PATH="$2"
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
[[ -n "$REGISTRY_NAME" ]] || fail "--registry-name is required"
[[ -n "$IMAGE_NAME" ]] || fail "--image-name is required"
[[ -n "$IMAGE_TAG" ]] || fail "--image-tag is required"
[[ -n "$BUILD_CONTEXT" ]] || fail "--context is required"
[[ -n "$DOCKERFILE_PATH" ]] || fail "--dockerfile is required"

[[ -d "$BUILD_CONTEXT" ]] || fail "Build context '$BUILD_CONTEXT' was not found"

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

if ! az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --output none >/dev/null 2>&1; then
  fail "Container registry '$REGISTRY_NAME' was not found in resource group '$RESOURCE_GROUP'"
fi

echo "Building and pushing image '$IMAGE_NAME:$IMAGE_TAG' with Azure Container Registry Tasks..."

az acr build \
  --registry "$REGISTRY_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  --file "$DOCKERFILE_PATH" \
  "$BUILD_CONTEXT"

LOGIN_SERVER=$(az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --query loginServer --output tsv)
[[ -n "$LOGIN_SERVER" ]] || fail "Failed to resolve registry login server"

echo "Image build completed."
echo "  Registry Name              : $REGISTRY_NAME"
echo "  Image Reference            : $LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"
echo "  Suggested env values:"
echo "    IMAGE_REFERENCE=$LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"