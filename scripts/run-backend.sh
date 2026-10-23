#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Demo launcher only: synthetic accounts/data and the browser token fallback are never production settings.
export RUMAH_APP_ENV=preview
export RUMAH_DEMO_MODE=1
export RUMAH_DEMO_SAMPLE_DATA=1
export RUMAH_BROWSER_SESSION_TOKEN=1
# Keep the synthetic preview away from the default persistent database path.
if [[ -z "${RUMAH_DB_PATH:-}" ]]; then
  PREVIEW_DB_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rumah-kecilku-preview.XXXXXX")"
  export RUMAH_DB_PATH="$PREVIEW_DB_DIR/rumah_kecilku.sqlite3"
fi
if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PYTHON="$ROOT/backend/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi
exec "$PYTHON" -m uvicorn app.main:app --app-dir "$ROOT/backend" --host 0.0.0.0 --port 8000 --reload --reload-dir "$ROOT/backend/app"
