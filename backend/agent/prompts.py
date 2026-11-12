"""Planner instructions. The model must return one JSON object."""

from __future__ import annotations

import json

from backend.agent.arms import ARMS, arm_clause
from backend.db.connection import sql_dialect

PLANNER_SYSTEM = """You are a data analyst orchestrator. Return one JSON object and nothing else.
Use these keys:
- next_step: execute_sql, run_python, both, fetch_context, or respond
- sql: a single read-only SELECT statement, or null
- python: analysis code, or null
- chart_type: bar, line, pie, scatter, histogram, or none
- answer: a short final answer only when next_step is respond, otherwise an empty string
- reasoning: one sentence

Rules:
- Answer counts, filters, rankings, and aggregations with execute_sql.
- Use run_python or both when the user wants a chart or a calculation on the query result.
- When both are needed, write Python that reads sql_result.json, a JSON list of records.
- Python may import pandas, numpy, and matplotlib only. Save the figure to chart.png. Do not call plt.show().
- Never emit INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, or PRAGMA.
- Use only tables and columns from the schema. Dialect: {dialect}.
- Do not invent numbers. If the schema cannot answer the question, respond and say so.
"""


def render_planner_input(state: dict) -> str:
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    sections = [
        f"Question:\n{state.get('question', '')}",
        arm_clause(arm),
        f"Schema:\n{state.get('schema_context') or '(none)'}",
    ]
    if state.get("profile_context"):
        sections.append(str(state["profile_context"]))
    if state.get("error"):
        sections.append(f"The previous attempt failed:\n{state['error']}")
        if state.get("sql_query"):
            sections.append(f"Previous SQL:\n{state['sql_query']}")
    preview = ((state.get("sql_result") or {}).get("rows") or [])[:5]
    if preview:
        sections.append("SQL preview rows:\n" + json.dumps(preview, default=str))
    sections.append("Return the JSON object now.")
    return "\n\n".join(sections)


def system_prompt() -> str:
    return PLANNER_SYSTEM.format(dialect=sql_dialect())
