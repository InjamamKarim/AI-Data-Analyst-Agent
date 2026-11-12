"""Graph state. Messages append; every other field is replaced by the node that writes it."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    question: str
    thread_id: str
    arm: str
    planner_mode: str
    hitl_enabled: bool
    fixed_plan: dict[str, Any]
    schema_context: Optional[str]
    profile_context: Optional[str]
    context_mode: str
    context_loaded: bool
    sql_query: Optional[str]
    blocked_sql: Optional[str]
    sql_result: Optional[dict[str, Any]]
    python_code: Optional[str]
    python_output: Optional[str]
    chart_path: Optional[str]
    chart_type: Optional[str]
    chart_valid: Optional[bool]
    next_step: str
    iteration: int
    tool_calls: int
    python_failures: int
    tokens: int
    error: Optional[str]
    answer: Optional[str]
    reasoning: Optional[str]
    blocked: bool
    rejected: bool
    approved: bool
    trace: list
    conversation_history: list
