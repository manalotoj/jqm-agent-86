#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h}"

if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Error: no Python interpreter found. Create .venv or install python3." >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import mcp' >/dev/null 2>&1; then
  echo "Error: optional MCP dependencies are not installed for ${PYTHON_BIN}. Run: pip install -r requirements.txt -r requirements-mcp.txt" >&2
  exit 1
fi

COMMON_ENV_FILE="${REPO_ROOT}/.env.common"
API_ENV_FILE="${REPO_ROOT}/.env.api"

cd "${REPO_ROOT}"

load_env_files() {
  local env_file

  set -a
  for env_file in "$@"; do
    if [[ -f "${env_file}" ]]; then
      source "${env_file}"
    fi
  done
  set +a
}

describe_env_files() {
  local label="$1"
  shift

  local env_file
  local found_any=0

  echo "${label} environment files:" >&2
  for env_file in "$@"; do
    if [[ -f "${env_file}" ]]; then
      echo "  - ${env_file:t}" >&2
      found_any=1
    fi
  done

  if (( found_any == 0 )); then
    echo "  - none found (expects environment variables to already be exported)" >&2
  fi
}

echo "Using Python: ${PYTHON_BIN}" >&2
describe_env_files "MCP" "${COMMON_ENV_FILE}" "${API_ENV_FILE}"
echo "Starting agent-86 MCP stdio server..." >&2

load_env_files "${COMMON_ENV_FILE}" "${API_ENV_FILE}"
PYTHONPATH="${REPO_ROOT}/src" exec "${PYTHON_BIN}" -m agent_86.mcp.server