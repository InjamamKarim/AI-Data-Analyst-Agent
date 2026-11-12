"""HTTP API and the chat page. The NVIDIA key is never returned."""

from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import __version__
from backend.agent.arms import ARMS
from backend.agent.service import get_session
from backend.config import AUDIT_PATH, CHART_DIR, UPLOAD_DIR, get_settings
from backend.db.connection import get_writer_engine, reset_engines
from backend.db.golden import GOLDEN_CASES
from backend.db.seed import seed_database
from backend.schema.catalog import get_catalog, invalidate_catalog
from backend.security.csv_sanitize import MAX_UPLOAD_BYTES, sanitize_dataframe
from backend.system_check import collect_host_status

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
EXAMPLE_IDS = ["q01", "q10", "q12", "q14", "q16", "q27", "q30", "q40"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seed_database(reset=False)
    logger.info("host %s", collect_host_status())
    yield


app = FastAPI(title="AI Data Analyst Agent", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None
    arm: str = "G"
    demo: bool = False
    hitl: bool = False


class ResumeIn(BaseModel):
    thread_id: str
    approved: bool = False


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "nvidia_api_key_configured": settings.nvidia_configured,
        "nvidia_model": settings.nvidia_model,
        "nvidia_base_url": settings.nvidia_base_url,
        "e2b": "ignored",
        "langsmith": "local-only",
        "database": "sqlite" if settings.use_sqlite else "external",
        "sandbox": "local",
        "hitl_default": settings.hitl_enabled,
        "host": collect_host_status(),
    }


@app.get("/api/arms")
def arms() -> list[dict]:
    return [{"id": arm.name, "title": arm.title} for arm in ARMS.values()]


@app.get("/api/examples")
def examples() -> list[dict]:
    by_id = {case["id"]: case for case in GOLDEN_CASES}
    return [
        {"id": case_id, "question": by_id[case_id]["question"], "chart_type": by_id[case_id]["chart_type"]}
        for case_id in EXAMPLE_IDS
    ]


@app.get("/api/schema")
def schema() -> list[dict]:
    return [
        {
            "name": table.name,
            "view": table.is_view,
            "columns": [column.name for column in table.columns],
            "description": table.description,
        }
        for table in get_catalog()
    ]


@app.post("/api/chat")
def chat(body: ChatIn) -> dict:
    question = body.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message is empty.")
    if body.arm not in ARMS:
        raise HTTPException(status_code=400, detail="Unknown arm.")
    mode = "scripted" if body.demo else "auto"
    return get_session().ask(
        question,
        arm=body.arm,
        planner_mode=mode,
        hitl=body.hitl,
        thread_id=body.thread_id,
    )


@app.post("/api/chat/resume")
def resume(body: ResumeIn) -> dict:
    if not body.thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required.")
    return get_session().resume(body.thread_id.strip(), body.approved)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV is larger than 5 MB.")
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")
    try:
        frame = pd.read_csv(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read that CSV.") from exc
    if frame.empty:
        raise HTTPException(status_code=400, detail="CSV has no rows.")
    cleaned = sanitize_dataframe(frame)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(UPLOAD_DIR / "latest.csv", index=False)
    settings = get_settings()
    loaded = False
    if settings.use_sqlite:
        cleaned.to_sql("uploaded_csv", get_writer_engine(), if_exists="replace", index=False)
        invalidate_catalog()
        reset_engines()
        loaded = True
    return {
        "rows": int(len(cleaned)),
        "columns": list(cleaned.columns),
        "sql_table": "uploaded_csv" if loaded else None,
    }


@app.get("/api/artifacts/{filename}")
def artifact(filename: str) -> FileResponse:
    if not re.fullmatch(r"chart_[a-f0-9]+\.png", filename):
        raise HTTPException(status_code=404, detail="Not found.")
    path = CHART_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/audit")
def audit(limit: int = 20) -> list[dict]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
