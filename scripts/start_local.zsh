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

if ! "${PYTHON_BIN}" -c 'import uvicorn' >/dev/null 2>&1; then
  echo "Error: uvicorn is not installed for ${PYTHON_BIN}. Run: pip install -r requirements.txt" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import streamlit' >/dev/null 2>&1; then
  echo "Error: streamlit is not installed for ${PYTHON_BIN}. Run: pip install -r requirements.txt" >&2
  exit 1
fi

API_HOST="127.0.0.1"
API_PORT="8000"
UI_PORT="8501"

COMMON_ENV_FILE="${REPO_ROOT}/.env.common"
API_ENV_FILE="${REPO_ROOT}/.env.api"
UI_ENV_FILE="${REPO_ROOT}/.env.ui"

typeset -i API_PID=0
typeset -i UI_PID=0

cleanup() {
  local exit_code=${1:-0}

  if (( UI_PID > 0 )) && kill -0 "${UI_PID}" 2>/dev/null; then
    kill "${UI_PID}" 2>/dev/null || true
  fi

  if (( API_PID > 0 )) && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi

  wait "${UI_PID}" 2>/dev/null || true
  wait "${API_PID}" 2>/dev/null || true

  exit "${exit_code}"
}

on_interrupt() {
  echo ""
  echo "Stopping local services..."
  cleanup 0
}

trap on_interrupt INT TERM

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

  echo "${label} environment files:"
  for env_file in "$@"; do
    if [[ -f "${env_file}" ]]; then
      echo "  - ${env_file:t}"
      found_any=1
    fi
  done

  if (( found_any == 0 )); then
    echo "  - none found (expects environment variables to already be exported)"
  fi
}

echo "Using Python: ${PYTHON_BIN}"
describe_env_files "API" "${COMMON_ENV_FILE}" "${API_ENV_FILE}"
echo "Starting API on http://${API_HOST}:${API_PORT}"
(
  load_env_files "${COMMON_ENV_FILE}" "${API_ENV_FILE}"
  export PYTHONPATH="${REPO_ROOT}/src"
  exec "${PYTHON_BIN}" -m uvicorn agent_86.main:app --reload --host "${API_HOST}" --port "${API_PORT}"
) &
API_PID=$!

describe_env_files "UI" "${COMMON_ENV_FILE}" "${UI_ENV_FILE}"
echo "Starting UI on http://${API_HOST}:${UI_PORT}"
(
  load_env_files "${COMMON_ENV_FILE}" "${UI_ENV_FILE}"
  exec "${PYTHON_BIN}" -m streamlit run "${REPO_ROOT}/dev_ui.py" --server.address "${API_HOST}" --server.port "${UI_PORT}"
) &
UI_PID=$!

echo ""
echo "agent-86 local development is starting:"
echo "  API docs: http://${API_HOST}:${API_PORT}/docs"
echo "  UI:       http://${API_HOST}:${UI_PORT}"
echo ""
echo "Press Ctrl+C to stop both services."

while true; do
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "API process exited. Shutting down UI..." >&2
    cleanup 1
  fi

  if ! kill -0 "${UI_PID}" 2>/dev/null; then
    echo "UI process exited. Shutting down API..." >&2
    cleanup 1
  fi

  sleep 1
done