#!/usr/bin/env python3
"""Copy the canonical backend KPSP catalog to the frontend offline fallback."""

from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / "backend" / "app" / "data" / "kpsp_forms.json"
target = root / "frontend" / "public" / "kpsp-catalog.json"
if not source.exists():
    raise SystemExit(f"Missing canonical catalog: {source}")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source, target)
print(f"Synced {source.relative_to(root)} → {target.relative_to(root)}")
