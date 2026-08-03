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

cd "${REPO_ROOT}"

echo "Using Python: ${PYTHON_BIN}" >&2
echo "Starting agent-86 MCP stdio server..." >&2

PYTHONPATH="${REPO_ROOT}/src" exec "${PYTHON_BIN}" -m agent_86.mcp.server