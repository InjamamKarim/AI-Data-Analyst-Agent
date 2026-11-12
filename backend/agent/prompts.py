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

Examples:
<input>Question: What was total revenue in Q1 2024?
Schema: [orders, order_items tables shown]</input>
<output>{{"next_step":"execute_sql","sql":"SELECT ROUND(SUM(oi.quantity*oi.unit_price*(1.0-oi.discount)),2) AS revenue FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE o.status='completed' AND o.order_date>='2024-01-01' AND o.order_date<'2024-04-01'","python":null,"chart_type":"none","answer":"","reasoning":"Revenue aggregation with date filter."}}</output>

<input>Question: Show a bar chart of sales by product category.
Schema: [orders, order_items, products tables shown]</input>
<output>{{"next_step":"both","sql":"SELECT p.category, ROUND(SUM(oi.quantity*oi.unit_price*(1.0-oi.discount)),2) AS sales FROM order_items oi JOIN orders o ON o.order_id=oi.order_id JOIN products p ON p.product_id=oi.product_id WHERE o.status='completed' GROUP BY p.category","python":"import pandas as pd, matplotlib.pyplot as plt, json\\ndata=json.load(open('sql_result.json'))\\ndf=pd.DataFrame(data)\\ndf.plot(kind='bar',x='category',y='sales',legend=False)\\nplt.tight_layout()\\nplt.savefig('chart.png')","chart_type":"bar","answer":"","reasoning":"Bar chart of sales by category requires SQL then Python."}}</output>

<input>Question: What is the average employee age?
Schema: [orders, order_items, customers tables shown]</input>
<output>{{"next_step":"respond","sql":null,"python":null,"chart_type":"none","answer":"The schema does not contain employee age data.","reasoning":"Cannot answer from available tables."}}</output>
"""

PLANNER_EXAMPLES = PLANNER_SYSTEM  # alias kept for external references


def render_planner_input(state: dict) -> str:
    arm = ARMS.get(state.get("arm") or "G", ARMS["G"])
    sections = [
        f"Question:\n{state.get('question', '')}",
        arm_clause(arm),
        f"Schema:\n{state.get('schema_context') or '(none)'}",
    ]
    if state.get("profile_context"):
        sections.append(str(state["profile_context"]))
    if state.get("conversation_history"):
        history_lines = []
        for turn in state["conversation_history"]:
            q = str(turn.get("q") or turn.get("question") or "")[:200]
            a = str(turn.get("answer") or "")[:200]
            history_lines.append(f"Q: {q}\nA: {a}")
        sections.insert(2, "Conversation history (most recent last):\n" + "\n---\n".join(history_lines))
    if state.get("error"):
        sections.append(f"The previous attempt failed:\n{state['error']}")
        if state.get("sql_query"):
            sections.append(f"Previous SQL:\n{state['sql_query']}")
    preview = ((state.get("sql_result") or {}).get("rows") or [])[:5]
    if preview:
        sections.append("SQL preview rows:\n" + json.dumps(preview, default=str))
    sections.append("Return the JSON object now.")
    return "\n\n".join(sections)


def system_prompt(arm_name: str = "G") -> str:
    base = PLANNER_SYSTEM.format(dialect=sql_dialect())
    if arm_name == "K":
        base += "\n\nThink step by step before returning the JSON. Write your reasoning in the 'reasoning' field (up to 3 sentences). Output the JSON object last."
    return base
