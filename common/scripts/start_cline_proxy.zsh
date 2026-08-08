#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h:h}"
BACKEND_VENV="${REPO_ROOT}/backend/.venv"
PROXY_PATH="${REPO_ROOT}/common/utils/cline/cline_proxy.py"

if [[ ! -x "${BACKEND_VENV}/bin/python" ]]; then
  echo "Error: backend/.venv not found. Set up the backend venv first." >&2
  exit 1
fi

"${BACKEND_VENV}/bin/python" -m uvicorn \
  --app-dir "${REPO_ROOT}/common/utils/cline" \
  cline_proxy:app --port 8787