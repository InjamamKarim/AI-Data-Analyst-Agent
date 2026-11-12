"""Per-turn working directory handed to the Python sandbox."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.config import ARTIFACT_DIR, CSV_DIR, UPLOAD_DIR


def workspace_for(thread_id: str | None) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", thread_id or "anon")[:80] or "anon"
    path = ARTIFACT_DIR / "work" / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_workspace(state: dict) -> Path:
    workspace = workspace_for(state.get("thread_id"))
    rows = ((state.get("sql_result") or {}).get("rows")) or []
    (workspace / "sql_result.json").write_text(json.dumps(rows, default=str), encoding="utf-8")
    if CSV_DIR.exists():
        for csv_file in CSV_DIR.glob("*.csv"):
            (workspace / csv_file.name).write_bytes(csv_file.read_bytes())
    upload = UPLOAD_DIR / "latest.csv"
    if upload.is_file():
        (workspace / "uploaded.csv").write_bytes(upload.read_bytes())
    return workspace
