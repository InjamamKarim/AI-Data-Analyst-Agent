"""Execute one reviewed SELECT and cap the rows that can re-enter the prompt."""

from __future__ import annotations

import math
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.db.connection import get_reader_engine
from backend.security.audit import audit_event, code_hash
from backend.security.sql_guard import review_sql


def run_select(query: str) -> dict[str, Any]:
    started = time.perf_counter()
    decision = review_sql(query)
    if not decision.allowed:
        audit_event("sql_blocked", sql_sha256=code_hash(query), reason=decision.reason)
        return _result(False, True, decision.reason, [], [], started)

    settings = get_settings()
    try:
        engine = get_reader_engine()
        with engine.connect() as conn:
            _arm_timeout(conn)
            result = conn.execute(text(decision.statement))
            columns = list(result.keys())
            fetched = result.fetchmany(settings.sql_fetch_rows + 1)
    except SQLAlchemyError as exc:
        message = f"SQL error: {exc.__class__.__name__}"
        audit_event("sql_error", sql_sha256=code_hash(decision.statement), error=message)
        return _result(False, False, message, [], [], started)

    truncated = len(fetched) > settings.sql_fetch_rows
    raw_rows = fetched[: settings.sql_fetch_rows]
    rows = [{key: _cell(value) for key, value in zip(columns, row)} for row in raw_rows]
    elapsed = time.perf_counter() - started
    audit_event(
        "sql_ok",
        sql_sha256=code_hash(decision.statement),
        rows=len(rows),
        truncated=truncated,
        elapsed_s=round(elapsed, 4),
    )
    payload = _result(True, False, None, columns, rows, started)
    payload["truncated"] = truncated
    return payload


def _arm_timeout(conn) -> None:
    try:
        dbapi = conn.connection
        driver = getattr(dbapi, "dbapi_connection", dbapi)
        deadline = time.time() + 15

        def _handler() -> int:
            return 1 if time.time() > deadline else 0

        if hasattr(driver, "set_progress_handler"):
            driver.set_progress_handler(_handler, 10000)
    except Exception:
        return


def _cell(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _result(ok: bool, blocked: bool, error: str | None, columns: list[str], rows: list[dict], started: float) -> dict[str, Any]:
    return {
        "ok": ok,
        "blocked": blocked,
        "error": error,
        "columns": columns,
        "rows": rows,
        "truncated": False,
        "elapsed_s": round(time.perf_counter() - started, 4),
    }
