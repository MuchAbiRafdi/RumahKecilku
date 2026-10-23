#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Workspace snapshots omit installed packages; restore them before launching the preview.
if [[ ! -x "$ROOT/node_modules/.bin/concurrently" || ! -x "$ROOT/frontend/node_modules/.bin/next" ]]; then
  npm ci --no-audit --no-fund
fi

# Python environments are also excluded from snapshots, so recreate the API environment as needed.
if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/backend/.venv"
fi
if ! "$ROOT/backend/.venv/bin/python" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  "$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"
fi

# This script is explicitly a synthetic-data preview, never a production launcher.
export RUMAH_APP_ENV=preview
export RUMAH_DEMO_MODE=1
export RUMAH_DEMO_SAMPLE_DATA=1
export RUMAH_BROWSER_SESSION_TOKEN=1
export NEXT_PUBLIC_DEMO_MODE=1

exec npm run dev:stack
