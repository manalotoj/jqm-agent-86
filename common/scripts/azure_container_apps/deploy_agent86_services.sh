#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
RESOURCE_GROUP=""
ENVIRONMENT_NAME="acae-agent86-dev"
REGISTRY_NAME="acragent86dev"
IMAGE_TAG="dev"

API_IMAGE_NAME="agent86-api"
MCP_IMAGE_NAME="agent86-mcp"
TOOLING_IMAGE_NAME="agent86-tooling"

API_APP_NAME="aca-agent86-api-dev"
MCP_APP_NAME="aca-agent86-mcp-dev"
TOOLING_APP_NAME="aca-agent86-tooling-dev"

API_DOCKERFILE="$REPO_ROOT/backend/Dockerfile.api"
MCP_DOCKERFILE="$REPO_ROOT/backend/Dockerfile.mcp"
TOOLING_DOCKERFILE="$REPO_ROOT/tooling/bicep-composition-service/Dockerfile"

API_CONTEXT="$REPO_ROOT/backend"
MCP_CONTEXT="$REPO_ROOT/backend"
TOOLING_CONTEXT="$REPO_ROOT/tooling/bicep-composition-service"

API_PORT="8000"
MCP_PORT="8001"
TOOLING_PORT="8080"

SKIP_BUILD=false
DEPLOY_MCP=false
API_EXTRA_ARGS=()
MCP_EXTRA_ARGS=()
TOOLING_EXTRA_ARGS=()

usage() {
  cat <<EOF
Usage: $(basename "$0") --resource-group <name> [options]

  Builds and deploys the hosted Agent 86 services:
  - main API
  - tooling/Bicep composition API

  Optional:
  - MCP server (only when --deploy-mcp is supplied)

Required:
  --resource-group <name>   Azure resource group containing the hosting resources

Optional:
  --environment-name <name> Container Apps environment name (default: $ENVIRONMENT_NAME)
  --registry-name <name>    Azure Container Registry name (default: $REGISTRY_NAME)
  --image-tag <tag>         Image tag for all services (default: $IMAGE_TAG)
  --api-dockerfile <path>   Dockerfile path for the API image (default: $API_DOCKERFILE)
  --mcp-dockerfile <path>   Dockerfile path for the MCP image (default: $MCP_DOCKERFILE)
  --tooling-dockerfile <path> Dockerfile path for the tooling image (default: $TOOLING_DOCKERFILE)
  --deploy-mcp              Build and deploy the MCP Container App
  --skip-build              Skip image builds and only update the Container Apps
  --api-env <KEY=VALUE>     Repeatable API env assignment
  --api-secret <KEY=VALUE>  Repeatable API secret assignment
  --mcp-env <KEY=VALUE>     Repeatable MCP env assignment
  --mcp-secret <KEY=VALUE>  Repeatable MCP secret assignment
  --tooling-env <KEY=VALUE> Repeatable tooling env assignment
  --tooling-secret <KEY=VALUE> Repeatable tooling secret assignment
  --help                    Show this help text

Notes:
  Dockerfiles default to the repo's checked-in production images.
  Override them with --api-dockerfile, --mcp-dockerfile, or --tooling-dockerfile if needed.
  MCP is skipped by default because the current server implementation is stdio-oriented.
  Use --deploy-mcp only when you explicitly want to publish the current MCP container shape.

Examples:
  Deploy API + tooling only:
    $(basename "$0") --resource-group rg-agent86-dev

  Deploy API + tooling + MCP:
    $(basename "$0") --resource-group rg-agent86-dev --deploy-mcp
EOF
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

add_assignment() {
  local -n target_ref=$1
  local value="$2"
  [[ "$value" == *=* ]] || fail "Assignments must use KEY=VALUE format"
  target_ref+=("$value")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group)
      [[ $# -ge 2 ]] || fail "Missing value for --resource-group"
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --environment-name)
      [[ $# -ge 2 ]] || fail "Missing value for --environment-name"
      ENVIRONMENT_NAME="$2"
      shift 2
      ;;
    --registry-name)
      [[ $# -ge 2 ]] || fail "Missing value for --registry-name"
      REGISTRY_NAME="$2"
      shift 2
      ;;
    --image-tag)
      [[ $# -ge 2 ]] || fail "Missing value for --image-tag"
      IMAGE_TAG="$2"
      shift 2
      ;;
    --api-dockerfile)
      [[ $# -ge 2 ]] || fail "Missing value for --api-dockerfile"
      API_DOCKERFILE="$2"
      shift 2
      ;;
    --mcp-dockerfile)
      [[ $# -ge 2 ]] || fail "Missing value for --mcp-dockerfile"
      MCP_DOCKERFILE="$2"
      shift 2
      ;;
    --tooling-dockerfile)
      [[ $# -ge 2 ]] || fail "Missing value for --tooling-dockerfile"
      TOOLING_DOCKERFILE="$2"
      shift 2
      ;;
    --deploy-mcp)
      DEPLOY_MCP=true
      shift
      ;;
    --skip-build)
      SKIP_BUILD=true
      shift
      ;;
    --api-env)
      [[ $# -ge 2 ]] || fail "Missing value for --api-env"
      add_assignment API_EXTRA_ARGS "$2"
      shift 2
      ;;
    --api-secret)
      [[ $# -ge 2 ]] || fail "Missing value for --api-secret"
      API_EXTRA_ARGS+=("__SECRET__::$2")
      shift 2
      ;;
    --mcp-env)
      [[ $# -ge 2 ]] || fail "Missing value for --mcp-env"
      add_assignment MCP_EXTRA_ARGS "$2"
      shift 2
      ;;
    --mcp-secret)
      [[ $# -ge 2 ]] || fail "Missing value for --mcp-secret"
      MCP_EXTRA_ARGS+=("__SECRET__::$2")
      shift 2
      ;;
    --tooling-env)
      [[ $# -ge 2 ]] || fail "Missing value for --tooling-env"
      add_assignment TOOLING_EXTRA_ARGS "$2"
      shift 2
      ;;
    --tooling-secret)
      [[ $# -ge 2 ]] || fail "Missing value for --tooling-secret"
      TOOLING_EXTRA_ARGS+=("__SECRET__::$2")
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

if [[ "$SKIP_BUILD" != true ]]; then
  [[ -n "$API_DOCKERFILE" ]] || fail "--api-dockerfile is required unless --skip-build is used"
  [[ -n "$TOOLING_DOCKERFILE" ]] || fail "--tooling-dockerfile is required unless --skip-build is used"
  if [[ "$DEPLOY_MCP" == true ]]; then
    [[ -n "$MCP_DOCKERFILE" ]] || fail "--mcp-dockerfile is required when --deploy-mcp is used unless --skip-build is used"
  fi
fi

az account show >/dev/null 2>&1 || fail "Azure CLI is not logged in. Run 'az login' first."

REGISTRY_LOGIN_SERVER=$(az acr show --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --query loginServer --output tsv)
[[ -n "$REGISTRY_LOGIN_SERVER" ]] || fail "Failed to resolve registry login server for '$REGISTRY_NAME'"

if [[ "$SKIP_BUILD" != true ]]; then
  bash "$SCRIPT_DIR/build_and_push_service_image.sh" \
    --resource-group "$RESOURCE_GROUP" \
    --registry-name "$REGISTRY_NAME" \
    --image-name "$TOOLING_IMAGE_NAME" \
    --image-tag "$IMAGE_TAG" \
    --context "$TOOLING_CONTEXT" \
    --dockerfile "$TOOLING_DOCKERFILE"

  echo ""

  if [[ "$DEPLOY_MCP" == true ]]; then
    bash "$SCRIPT_DIR/build_and_push_service_image.sh" \
      --resource-group "$RESOURCE_GROUP" \
      --registry-name "$REGISTRY_NAME" \
      --image-name "$MCP_IMAGE_NAME" \
      --image-tag "$IMAGE_TAG" \
      --context "$MCP_CONTEXT" \
      --dockerfile "$MCP_DOCKERFILE"

    echo ""
  fi

  bash "$SCRIPT_DIR/build_and_push_service_image.sh" \
    --resource-group "$RESOURCE_GROUP" \
    --registry-name "$REGISTRY_NAME" \
    --image-name "$API_IMAGE_NAME" \
    --image-tag "$IMAGE_TAG" \
    --context "$API_CONTEXT" \
    --dockerfile "$API_DOCKERFILE"

  echo ""
fi

build_args() {
  local -n source_ref=$1
  local -n env_ref=$2
  local -n secret_ref=$3
  local item
  for item in "${source_ref[@]}"; do
    if [[ "$item" == __SECRET__::* ]]; then
      secret_ref+=(--secret "${item#__SECRET__::}")
    else
      env_ref+=(--env "$item")
    fi
  done
}

TOOLING_ENV_ARGS=()
TOOLING_SECRET_ARGS=()
build_args TOOLING_EXTRA_ARGS TOOLING_ENV_ARGS TOOLING_SECRET_ARGS

bash "$SCRIPT_DIR/create_container_app.sh" \
  --resource-group "$RESOURCE_GROUP" \
  --app-name "$TOOLING_APP_NAME" \
  --environment-name "$ENVIRONMENT_NAME" \
  --image "$REGISTRY_LOGIN_SERVER/$TOOLING_IMAGE_NAME:$IMAGE_TAG" \
  --target-port "$TOOLING_PORT" \
  --ingress internal \
  --registry-server "$REGISTRY_LOGIN_SERVER" \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 0 \
  --max-replicas 1 \
  "${TOOLING_ENV_ARGS[@]}" \
  "${TOOLING_SECRET_ARGS[@]}"

echo ""

MCP_ENV_ARGS=()
MCP_SECRET_ARGS=()
build_args MCP_EXTRA_ARGS MCP_ENV_ARGS MCP_SECRET_ARGS

if [[ "$DEPLOY_MCP" == true ]]; then
  bash "$SCRIPT_DIR/create_container_app.sh" \
    --resource-group "$RESOURCE_GROUP" \
    --app-name "$MCP_APP_NAME" \
    --environment-name "$ENVIRONMENT_NAME" \
    --image "$REGISTRY_LOGIN_SERVER/$MCP_IMAGE_NAME:$IMAGE_TAG" \
    --target-port "$MCP_PORT" \
    --ingress internal \
    --registry-server "$REGISTRY_LOGIN_SERVER" \
    --cpu 0.5 \
    --memory 1.0Gi \
    --min-replicas 0 \
    --max-replicas 1 \
    "${MCP_ENV_ARGS[@]}" \
    "${MCP_SECRET_ARGS[@]}"

  echo ""
fi

API_ENV_ARGS=()
API_SECRET_ARGS=()
build_args API_EXTRA_ARGS API_ENV_ARGS API_SECRET_ARGS

API_ENV_ARGS+=(--env "BICEP_COMPOSITION_BASE_URL=http://$TOOLING_APP_NAME")
if [[ "$DEPLOY_MCP" == true ]]; then
  API_ENV_ARGS+=(--env "MCP_BASE_URL=http://$MCP_APP_NAME")
fi

bash "$SCRIPT_DIR/create_container_app.sh" \
  --resource-group "$RESOURCE_GROUP" \
  --app-name "$API_APP_NAME" \
  --environment-name "$ENVIRONMENT_NAME" \
  --image "$REGISTRY_LOGIN_SERVER/$API_IMAGE_NAME:$IMAGE_TAG" \
  --target-port "$API_PORT" \
  --ingress external \
  --registry-server "$REGISTRY_LOGIN_SERVER" \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 2 \
  "${API_ENV_ARGS[@]}" \
  "${API_SECRET_ARGS[@]}"

echo ""
echo "Completed Agent 86 service deployment."
echo "  API App                    : $API_APP_NAME"
if [[ "$DEPLOY_MCP" == true ]]; then
  echo "  MCP App                    : $MCP_APP_NAME"
else
  echo "  MCP App                    : skipped (use --deploy-mcp to enable)"
fi
echo "  Tooling App                : $TOOLING_APP_NAME"
echo "  Registry                   : $REGISTRY_NAME"
echo "  Image Tag                  : $IMAGE_TAG"