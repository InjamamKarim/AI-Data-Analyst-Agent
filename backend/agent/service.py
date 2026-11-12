"""Run one turn and resume a paused human review on the same checkpoint."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import Command

from backend.agent.graph import compile_graph
from backend.config import CHART_DIR
from backend.security.audit import trace_event

logger = logging.getLogger(__name__)

try:
    from langgraph.errors import GraphInterrupt
except ImportError:  # pragma: no cover - older langgraph
    class GraphInterrupt(Exception):
        pass

try:
    from langgraph.checkpoint.memory import InMemorySaver as _Saver
except ImportError:  # pragma: no cover
    from langgraph.checkpoint.memory import MemorySaver as _Saver


class Session:
    def __init__(self, checkpointer=None) -> None:
        self.checkpointer = checkpointer or _Saver()
        self.graph = compile_graph(self.checkpointer)

    def ask(
        self,
        question: str,
        *,
        arm: str = "G",
        planner_mode: str = "auto",
        hitl: bool | None = None,
        thread_id: str | None = None,
        fixed_plan: dict | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        thread_id = thread_id or uuid.uuid4().hex
        mode = "fixed" if fixed_plan is not None else planner_mode
        from backend.config import get_settings

        settings = get_settings()
        hitl_enabled = settings.hitl_enabled if hitl is None else hitl
        payload: dict[str, Any] = {
            "question": question,
            "arm": arm,
            "planner_mode": mode,
            "hitl_enabled": hitl_enabled,
            "thread_id": thread_id,
            "messages": [{"role": "user", "content": question}],
        }
        if fixed_plan is not None:
            payload["fixed_plan"] = fixed_plan
        config = {"configurable": {"thread_id": thread_id}}
        # Inject conversation history from prior checkpoint for this thread.
        try:
            snapshot = self.graph.get_state(config)
            if snapshot and snapshot.values:
                prior_history = list(snapshot.values.get("conversation_history") or [])
                if prior_history:
                    payload["conversation_history"] = prior_history[-3:]
        except Exception:
            logger.exception("could not read prior checkpoint for conversation_history")
        trace_event("turn_start", thread_id=thread_id, arm=arm, planner_mode=mode)
        try:
            self.graph.invoke(payload, config)
        except GraphInterrupt:
            pass
        except Exception:
            logger.exception("agent failed")
            return _failed(thread_id, arm, mode, started)
        return self._from_checkpoint(config, thread_id, started)

    def resume(self, thread_id: str, approved: bool) -> dict[str, Any]:
        started = time.perf_counter()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            self.graph.invoke(Command(resume={"approved": bool(approved)}), config)
        except GraphInterrupt:
            pass
        except Exception:
            logger.exception("resume failed")
            arm, mode = self._checkpoint_labels(config)
            return _failed(thread_id, arm, mode, started)
        return self._from_checkpoint(config, thread_id, started)

    def _checkpoint_labels(self, config: dict) -> tuple[str, str]:
        try:
            snapshot = self.graph.get_state(config)
            values = dict(getattr(snapshot, "values", None) or {})
        except Exception:
            logger.exception("could not read checkpoint metadata")
            values = {}
        return str(values.get("arm") or "G"), str(values.get("planner_mode") or "auto")

    def _from_checkpoint(self, config: dict, thread_id: str, started: float) -> dict[str, Any]:
        snapshot = self.graph.get_state(config)
        pending = _interrupt_value(snapshot)
        values = dict(snapshot.values or {})
        latency = round(time.perf_counter() - started, 3)
        if pending is not None:
            payload = pending if isinstance(pending, dict) else {"message": str(pending)}
            return {
                "output": "Waiting for approval before this plan runs.",
                "sql": None,
                "blocked_sql": None,
                "rows": [],
                "columns": [],
                "python": payload.get("python") if isinstance(payload, dict) else None,
                "python_output": None,
                "chart_path": None,
                "chart_url": None,
                "chart_valid": None,
                "blocked": False,
                "rejected": False,
                "error": None,
                "tokens": values.get("tokens") or 0,
                "arm": values.get("arm"),
                "planner_mode": values.get("planner_mode"),
                "demo": values.get("planner_mode") == "scripted",
                "trace": values.get("trace") or [],
                "interrupted": True,
                "interrupt": payload,
                "thread_id": thread_id,
                "latency_s": latency,
            }
        return _public_result(values, thread_id, latency)


_singleton: Session | None = None
_lock = threading.Lock()


def get_session() -> Session:
    global _singleton
    with _lock:
        if _singleton is None:
            _singleton = Session()
        return _singleton


def _public_result(values: dict, thread_id: str, latency: float) -> dict[str, Any]:
    blocked = bool(values.get("blocked"))
    rows = ((values.get("sql_result") or {}).get("rows")) or []
    columns = list(rows[0].keys()) if rows else ((values.get("sql_result") or {}).get("columns") or [])
    chart_path = values.get("chart_path")
    return {
        "output": values.get("answer") or "",
        "sql": None if blocked or values.get("rejected") else values.get("sql_query"),
        "blocked_sql": values.get("blocked_sql"),
        "rows": rows,
        "columns": columns,
        "python": values.get("python_code"),
        "python_output": values.get("python_output"),
        "chart_path": chart_path,
        "chart_url": _chart_url(chart_path),
        "chart_valid": values.get("chart_valid"),
        "blocked": blocked,
        "rejected": bool(values.get("rejected")),
        "error": values.get("error"),
        "sql_elapsed_s": (values.get("sql_result") or {}).get("elapsed_s"),
        "tokens": values.get("tokens") or 0,
        "arm": values.get("arm"),
        "planner_mode": values.get("planner_mode"),
        "demo": values.get("planner_mode") == "scripted",
        "trace": values.get("trace") or [],
        "conversation_history": values.get("conversation_history") or [],
        "interrupted": False,
        "interrupt": None,
        "thread_id": values.get("thread_id") or thread_id,
        "latency_s": latency,
    }


def _chart_url(path: str | None) -> str | None:
    if not path:
        return None
    file = Path(path)
    try:
        file.resolve().relative_to(CHART_DIR.resolve())
    except ValueError:
        return None
    return f"/api/artifacts/{file.name}"


def _interrupt_value(snapshot) -> Any:
    interrupts = getattr(snapshot, "interrupts", None) or ()
    if interrupts:
        return getattr(interrupts[0], "value", interrupts[0])
    for task in getattr(snapshot, "tasks", ()) or ():
        pending = getattr(task, "interrupts", None) or ()
        if pending:
            return getattr(pending[0], "value", pending[0])
    return None


def _failed(thread_id: str, arm: str, mode: str, started: float) -> dict[str, Any]:
    return {
        "output": "The agent hit an unexpected error and stopped before finishing this turn.",
        "sql": None,
        "blocked_sql": None,
        "rows": [],
        "columns": [],
        "python": None,
        "python_output": None,
        "chart_path": None,
        "chart_url": None,
        "chart_valid": None,
        "blocked": False,
        "rejected": False,
        "error": "internal_error",
        "tokens": 0,
        "arm": arm,
        "planner_mode": mode,
        "demo": mode == "scripted",
        "trace": [],
        "interrupted": False,
        "interrupt": None,
        "thread_id": thread_id,
        "latency_s": round(time.perf_counter() - started, 3),
    }
