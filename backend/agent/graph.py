"""Explicit LangGraph: prepare, plan, optional human review, SQL, Python, chart check, answer."""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.agent.arms import ARMS, apply_arm_policy
from backend.agent.format import draft_answer
from backend.agent.planner import RoutingPlanner
from backend.agent.state import AgentState
from backend.config import estimate_tokens, get_settings
from backend.llm.nvidia import MissingAPIKeyError
from backend.sandbox.local_sandbox import execute_in_sandbox
from backend.schema.catalog import get_catalog
from backend.schema.context import build_schema_context, semantic_document
from backend.schema.profile import build_profile
from backend.security.audit import audit_event, code_hash
from backend.security.sql_guard import user_requests_destruction
from backend.tools.charts import validate_chart
from backend.tools.sql_tool import run_select
from backend.tools.workspace import prepare_workspace

logger = logging.getLogger(__name__)


def compile_graph(checkpointer):
    planner = RoutingPlanner()
    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare_node)
    graph.add_node("planner", lambda state: planner_node(state, planner))
    graph.add_node("hitl", hitl_node)
    graph.add_node("fetch_context", fetch_context_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("run_python", run_python_node)
    graph.add_node("chart_review", chart_review_node)
    graph.add_node("synthesize", synthesize_node)

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges(
        "prepare",
        route_after_prepare,
        {"planner": "planner", "synthesize": "synthesize"},
    )
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "hitl": "hitl",
            "execute_sql": "execute_sql",
            "run_python": "run_python",
            "fetch_context": "fetch_context",
            "synthesize": "synthesize",
        },
    )
    graph.add_conditional_edges(
        "hitl",
        route_after_hitl,
        {"execute_sql": "execute_sql", "run_python": "run_python", "synthesize": "synthesize"},
    )
    graph.add_edge("fetch_context", "planner")
    graph.add_conditional_edges(
        "execute_sql",
        route_after_sql,
        {"run_python": "run_python", "planner": "planner", "synthesize": "synthesize"},
    )
    graph.add_conditional_edges(
        "run_python",
        route_after_python,
        {"chart_review": "chart_review", "planner": "planner", "synthesize": "synthesize"},
    )
    graph.add_conditional_edges(
        "chart_review",
        route_after_chart,
        {"planner": "planner", "synthesize": "synthesize"},
    )
    graph.add_edge("synthesize", END)
    return graph.compile(checkpointer=checkpointer)


def prepare_node(state: AgentState) -> dict:
    question = (state.get("question") or _latest_question(state)).strip()
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    if user_requests_destruction(question):
        message = "BLOCKED: Destructive operations are not permitted."
        audit_event("intent_blocked", thread_id=state.get("thread_id"), question=question[:300])
        return {
            "question": question,
            "blocked": True,
            "rejected": False,
            "error": message,
            "answer": message,
            "next_step": "respond",
            "sql_query": None,
            "sql_result": None,
            "python_code": None,
            "python_output": None,
            "chart_path": None,
            "schema_context": "",
            "profile_context": "",
            "iteration": 0,
            "tool_calls": 0,
            "python_failures": 0,
            "tokens": estimate_tokens(question),
            "trace": [{"node": "prepare", "blocked": True}],
        }

    schema, names = build_schema_context(
        question,
        filter_schema=arm.schema_filter,
        mode=arm.context_mode,
    )
    profile = ""
    if arm.guidance and arm.context_mode != "tool":
        selected = [table for table in get_catalog() if table.name in names and not table.is_view]
        try:
            profile = build_profile(selected)
        except Exception:
            logger.exception("profile failed")
            profile = ""
    return {
        "question": question,
        "blocked": False,
        "rejected": False,
        "approved": not bool(state.get("hitl_enabled")),
        "error": None,
        "answer": None,
        "sql_query": None,
        "blocked_sql": None,
        "sql_result": None,
        "python_code": None,
        "python_output": None,
        "chart_path": None,
        "chart_type": "none",
        "chart_valid": None,
        "schema_context": schema,
        "profile_context": profile,
        "context_mode": arm.context_mode,
        "context_loaded": arm.context_mode != "tool",
        "iteration": 0,
        "tool_calls": 0,
        "python_failures": 0,
        "tokens": estimate_tokens(question) + estimate_tokens(schema) + estimate_tokens(profile),
        "trace": [
            {
                "node": "prepare",
                "blocked": False,
                "tables": names,
                "profile_included": bool(profile),
                "context_mode": arm.context_mode,
            }
        ],
    }


def planner_node(state: AgentState, planner: RoutingPlanner) -> dict:
    settings = get_settings()
    iteration = int(state.get("iteration") or 0) + 1
    if state.get("blocked"):
        return {"iteration": iteration, "next_step": "respond", "answer": state.get("error")}
    if iteration > settings.max_iterations or int(state.get("tool_calls") or 0) >= settings.max_tool_calls:
        return {
            "iteration": iteration,
            "next_step": "respond",
            "answer": state.get("answer") or "Stopped: the step budget was reached.",
        }
    if int(state.get("tokens") or 0) >= settings.token_budget:
        return {
            "iteration": iteration,
            "next_step": "respond",
            "answer": "Stopped: the token budget was reached.",
        }
    try:
        plan = planner.plan(state)
    except MissingAPIKeyError as exc:
        return {
            "iteration": iteration,
            "next_step": "respond",
            "answer": str(exc),
            "error": "missing_api_key",
        }
    plan = apply_arm_policy(plan, state.get("arm") or "G")
    if plan.get("next_step") == "fetch_context" and state.get("context_loaded"):
        plan["next_step"] = "execute_sql" if plan.get("sql") else "respond"
    tokens = int(state.get("tokens") or 0) + int(plan.get("tokens") or estimate_tokens(str(plan)))
    audit_event(
        "plan",
        thread_id=state.get("thread_id"),
        arm=state.get("arm"),
        next_step=plan.get("next_step"),
        sql_sha256=code_hash(plan.get("sql")),
        python_sha256=code_hash(plan.get("python")),
        planner_mode=state.get("planner_mode"),
    )
    return {
        "iteration": iteration,
        "tokens": tokens,
        "next_step": plan.get("next_step") or "respond",
        "sql_query": plan.get("sql"),
        "python_code": plan.get("python"),
        "chart_type": plan.get("chart_type") or "none",
        "answer": plan.get("answer") or None,
        "reasoning": plan.get("reasoning"),
        "error": None,
        "trace": _append(state, "planner", next_step=plan.get("next_step")),
    }


def hitl_node(state: AgentState) -> dict:
    decision = interrupt(
        {
            "type": "approve_plan",
            "message": "Review this plan before it runs.",
            "question": state.get("question"),
            "sql": state.get("sql_query"),
            "python": state.get("python_code"),
            "chart_type": state.get("chart_type"),
        }
    )
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    if not approved:
        query = state.get("sql_query")
        audit_event("plan_rejected", thread_id=state.get("thread_id"), sql_sha256=code_hash(query))
        return {
            "approved": False,
            "rejected": True,
            "next_step": "respond",
            "sql_query": None,
            "blocked_sql": query,
            "answer": "This plan was not approved, so nothing ran.",
            "trace": _append(state, "hitl", approved=False),
        }
    audit_event("plan_approved", thread_id=state.get("thread_id"), sql_sha256=code_hash(state.get("sql_query")))
    return {"approved": True, "rejected": False, "trace": _append(state, "hitl", approved=True)}


def fetch_context_node(state: AgentState) -> dict:
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    document = semantic_document(state.get("question") or "", arm.schema_filter)
    audit_event("fetch_context", thread_id=state.get("thread_id"), chars=len(document))
    return {
        "schema_context": document,
        "context_loaded": True,
        "tokens": int(state.get("tokens") or 0) + estimate_tokens(document),
        "trace": _append(state, "fetch_context"),
    }


def execute_sql_node(state: AgentState) -> dict:
    query = state.get("sql_query") or ""
    if state.get("hitl_enabled") and not state.get("approved"):
        message = "BLOCKED: plan was not approved."
        return {
            "blocked": True,
            "error": message,
            "answer": message,
            "next_step": "respond",
            "sql_result": None,
            "sql_query": None,
            "blocked_sql": query,
            "trace": _append(state, "execute_sql", blocked=True),
        }
    outcome = run_select(query)
    calls = int(state.get("tool_calls") or 0) + 1
    if outcome["blocked"]:
        return {
            "blocked": True,
            "error": outcome["error"],
            "answer": outcome["error"],
            "sql_result": outcome,
            "sql_query": None,
            "blocked_sql": query,
            "tool_calls": calls,
            "next_step": "respond",
            "trace": _append(state, "execute_sql", blocked=True),
        }
    if not outcome["ok"]:
        return {
            "error": outcome["error"],
            "sql_result": outcome,
            "tool_calls": calls,
            "iteration": int(state.get("iteration") or 0) + 1,
            "trace": _append(state, "execute_sql", ok=False),
        }
    return {
        "error": None,
        "blocked": False,
        "sql_result": outcome,
        "tool_calls": calls,
        "trace": _append(state, "execute_sql", ok=True, rows=len(outcome["rows"])),
    }


def run_python_node(state: AgentState) -> dict:
    failures = int(state.get("python_failures") or 0)
    calls = int(state.get("tool_calls") or 0) + 1
    if failures >= 3:
        return {
            "error": "Python sandbox failed three times.",
            "next_step": "respond",
            "tool_calls": calls,
        }
    workspace = prepare_workspace(state)
    outcome = execute_in_sandbox(state.get("python_code") or "", workspace)
    audit_event(
        "python",
        thread_id=state.get("thread_id"),
        ok=outcome.ok,
        python_sha256=code_hash(state.get("python_code")),
        error=(outcome.error or "")[:300],
    )
    if not outcome.ok:
        return {
            "python_output": outcome.stdout,
            "error": outcome.error or outcome.stderr or "Python execution failed.",
            "python_failures": failures + 1,
            "iteration": int(state.get("iteration") or 0) + 1,
            "tool_calls": calls,
            "chart_path": outcome.chart_path,
            "trace": _append(state, "run_python", ok=False),
        }
    return {
        "python_output": outcome.stdout,
        "error": None,
        "chart_path": outcome.chart_path,
        "tool_calls": calls,
        "trace": _append(state, "run_python", ok=True, chart=bool(outcome.chart_path)),
    }


def chart_review_node(state: AgentState) -> dict:
    valid, reason = validate_chart(state.get("python_code"), state.get("chart_path"), state.get("chart_type"))
    audit_event("chart_review", thread_id=state.get("thread_id"), valid=valid, reason=reason)
    if valid:
        return {"chart_valid": True, "error": None, "trace": _append(state, "chart_review", valid=True)}
    return {
        "chart_valid": False,
        "error": f"Chart check failed: {reason}",
        "python_failures": int(state.get("python_failures") or 0) + 1,
        "iteration": int(state.get("iteration") or 0) + 1,
        "trace": _append(state, "chart_review", valid=False, reason=reason),
    }


def synthesize_node(state: AgentState) -> dict:
    answer = draft_answer(state)
    tokens = int(state.get("tokens") or 0)
    if (
        state.get("planner_mode") == "auto"
        and get_settings().nvidia_configured
        and not state.get("blocked")
        and not state.get("rejected")
        and (state.get("sql_result") or {}).get("ok")
    ):
        try:
            from backend.llm.nvidia import complete

            rows = (state.get("sql_result") or {}).get("rows") or []
            phrased, used = complete(
                "You write a short factual answer for an analyst. Use only the numbers in the rows. "
                "If a number is not in the rows, say the result is in the table. Two to four sentences.",
                f"Question: {state.get('question')}\nRows: {rows[:20]}",
            )
            answer = phrased.strip()
            tokens += used
        except Exception:
            logger.exception("answer phrasing failed")
    audit_event(
        "answer",
        thread_id=state.get("thread_id"),
        blocked=bool(state.get("blocked")),
        rejected=bool(state.get("rejected")),
        tokens=tokens,
    )
    history = list(state.get("conversation_history") or [])
    history.append({
        "q": state.get("question"),
        "answer": answer[:300],
        "sql": state.get("sql_query"),
    })
    history = history[-6:]
    return {
        "answer": answer,
        "tokens": tokens,
        "messages": [{"role": "assistant", "content": answer}],
        "trace": _append(state, "synthesize"),
        "conversation_history": history,
    }


def route_after_prepare(state: AgentState) -> str:
    if state.get("blocked"):
        return "synthesize"
    return "planner"


def route_after_planner(state: AgentState) -> str:
    if state.get("error") == "missing_api_key":
        return "synthesize"
    step = state.get("next_step") or "respond"
    if step == "respond":
        return "synthesize"
    if step == "fetch_context":
        return "fetch_context"
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    needs_review = bool(state.get("hitl_enabled"))
    if step in {"execute_sql", "both"} and arm.use_sql and state.get("sql_query"):
        return "hitl" if needs_review else "execute_sql"
    if step == "run_python" and arm.use_python and state.get("python_code"):
        return "hitl" if needs_review else "run_python"
    return "synthesize"


def route_after_hitl(state: AgentState) -> str:
    if not state.get("approved"):
        return "synthesize"
    step = state.get("next_step")
    if step in {"execute_sql", "both"} and state.get("sql_query"):
        return "execute_sql"
    if step == "run_python" and state.get("python_code"):
        return "run_python"
    return "synthesize"


def route_after_sql(state: AgentState) -> str:
    if state.get("blocked"):
        return "synthesize"
    if state.get("error"):
        if int(state.get("iteration") or 0) >= get_settings().max_iterations:
            return "synthesize"
        return "planner"
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    if (
        state.get("next_step") == "both"
        and arm.use_python
        and state.get("python_code")
        and int(state.get("python_failures") or 0) < 3
    ):
        return "run_python"
    return "synthesize"


def route_after_python(state: AgentState) -> str:
    if state.get("error"):
        if int(state.get("python_failures") or 0) >= 3 or int(state.get("iteration") or 0) >= get_settings().max_iterations:
            return "synthesize"
        return "planner"
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    chart_type = state.get("chart_type") or "none"
    if arm.chart_agent and chart_type != "none":
        return "chart_review"
    return "synthesize"


def route_after_chart(state: AgentState) -> str:
    if state.get("chart_valid"):
        return "synthesize"
    if int(state.get("python_failures") or 0) >= 3 or int(state.get("iteration") or 0) >= get_settings().max_iterations:
        return "synthesize"
    return "planner"


def _append(state: AgentState, node: str, **fields) -> list:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, **fields})
    return trace[-40:]


def _latest_question(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return str(last.get("content") or "")
    return str(getattr(last, "content", "") or "")
