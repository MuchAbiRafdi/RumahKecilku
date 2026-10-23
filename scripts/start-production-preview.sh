#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Workspace snapshots omit installed packages; restore them inside the long-lived preview process.
if [[ ! -x "$ROOT/node_modules/.bin/concurrently" || ! -x "$ROOT/frontend/node_modules/.bin/next" ]]; then
  npm ci --no-audit --no-fund
fi

# Python environments are also omitted from snapshots.
if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/backend/.venv"
fi
if ! "$ROOT/backend/.venv/bin/python" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  "$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"
fi

# Despite the script name, this is an embedded preview with synthetic data, not a production deployment.
export RUMAH_APP_ENV=preview
export RUMAH_DEMO_MODE=1
export RUMAH_DEMO_SAMPLE_DATA=1
export RUMAH_BROWSER_SESSION_TOKEN=1
export NEXT_PUBLIC_DEMO_MODE=1

npm run typecheck
npm run build

# Wait for API health before exposing the UI, avoiding a startup-time proxy race.
exec "$ROOT/node_modules/.bin/concurrently" --kill-others --names API,WEB --prefix-colors cyan,magenta \
  "npm run dev:api" \
  "bash -c 'for attempt in {1..80}; do if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then exec npm run start --workspace frontend; fi; sleep 0.25; done; echo API_not_ready_after_20s >&2; exit 1'"
