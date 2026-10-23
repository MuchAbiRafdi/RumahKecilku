#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  python3 -m venv "$ROOT/backend/.venv"
fi
if ! "$PYTHON" -c 'import fastapi, pytest' >/dev/null 2>&1; then
  "$PYTHON" -m pip install -r "$ROOT/backend/requirements-dev.txt"
fi
cd "$ROOT/backend"
exec "$PYTHON" -m pytest -q
