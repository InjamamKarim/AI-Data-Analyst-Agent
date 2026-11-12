"""Planners: NVIDIA when a key is present, curated SQL for demo mode, fixed plans for tests."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.agent.prompts import render_planner_input, system_prompt
from backend.db.golden import lookup_case
from backend.llm.nvidia import complete

_STEPS = {"execute_sql", "run_python", "both", "fetch_context", "respond"}
_CHARTS = {"bar", "line", "pie", "scatter", "histogram", "none"}

DEMO_MISS = (
    "Demo mode only runs the 60 curated sample questions, and this one is not in that set. "
    "Pick an example question, or add your free NVIDIA_API_KEY to .env and turn demo mode off."
)


class ScriptedPlanner:
    """Replays the Golden 60. This path is labeled demo and is not a model score."""

    def plan(self, state: dict) -> dict[str, Any]:
        if state.get("context_mode") == "tool" and not state.get("context_loaded"):
            return _plan("fetch_context", reasoning="Load the semantic notes first.")
        case = lookup_case(state.get("question") or "")
        if case is None:
            return _plan("respond", answer=DEMO_MISS, reasoning="Question is outside the demo set.")
        if case.get("python"):
            return _plan(
                "both",
                sql=case["sql"],
                python=case["python"],
                chart_type=case.get("chart_type") or "none",
                reasoning="Demo case with a chart.",
            )
        return _plan("execute_sql", sql=case["sql"], reasoning="Demo case.")


class NvidiaPlanner:
    def plan(self, state: dict) -> dict[str, Any]:
        arm = state.get("arm") or "G"
        prompt = system_prompt(arm)
        user_input = render_planner_input(state)
        text, tokens = complete(prompt, user_input)
        try:
            plan = parse_plan(text)
        except (json.JSONDecodeError, ValueError):
            # Attempt one repair retry
            try:
                repair_prompt = (
                    "Fix this broken JSON to match the schema "
                    "{next_step, sql, python, chart_type, answer, reasoning}. "
                    "Return ONLY valid JSON and nothing else:\n" + text[:800]
                )
                repaired_text, repair_tokens = complete(
                    "You are a JSON repair tool. Return only a valid JSON object.",
                    repair_prompt,
                )
                tokens += repair_tokens
                plan = parse_plan(repaired_text)
            except Exception:
                plan = _plan(
                    "respond",
                    answer="The model did not return a usable plan. Try rephrasing the question.",
                    reasoning="JSON parse failed.",
                )
        plan["tokens"] = tokens
        return plan


class RoutingPlanner:
    def plan(self, state: dict) -> dict[str, Any]:
        mode = state.get("planner_mode") or "auto"
        if mode == "fixed":
            if state.get("sql_result") or state.get("blocked") or state.get("error"):
                return _plan("respond", reasoning="Stop after the tool result.")
            return dict(state.get("fixed_plan") or _plan("respond", answer="No plan was provided."))
        if mode == "scripted":
            return ScriptedPlanner().plan(state)
        if mode != "auto":
            return _plan(
                "respond",
                answer=(
                    f"Unknown planner mode '{mode}'. "
                    "Use auto for the NVIDIA model, scripted for the sample questions, or fixed for a supplied plan."
                ),
                reasoning="Unknown planner mode.",
            )
        return NvidiaPlanner().plan(state)


def _extract_json_substring(text: str) -> str:
    # 1. Try markdown fenced block: ```json ... ``` or ``` ... ```
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    # 2. Find outermost matching braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1].strip()

    # 3. Fallback: regex search
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    raise ValueError("Planner output did not contain JSON.")


def parse_plan(text: str) -> dict[str, Any]:
    raw_json = _extract_json_substring(text)
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # Simple fixup for trailing commas before closing braces
        cleaned = re.sub(r",\s*([\}\]])", r"\1", raw_json)
        data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Planner JSON was not an object.")
    step = str(data.get("next_step") or "respond")
    if step not in _STEPS:
        step = "respond"
    chart = str(data.get("chart_type") or "none")
    if chart not in _CHARTS:
        chart = "none"
    return _plan(
        step,
        sql=_clean(data.get("sql")),
        python=_clean(data.get("python")),
        chart_type=chart,
        answer=str(data.get("answer") or "").strip(),
        reasoning=str(data.get("reasoning") or "").strip(),
    )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "null", "none"}:
        return None
    fenced = re.search(r"```(?:sql|python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    return text or None


def _plan(
    step: str,
    sql: str | None = None,
    python: str | None = None,
    chart_type: str = "none",
    answer: str = "",
    reasoning: str = "",
) -> dict[str, Any]:
    return {
        "next_step": step,
        "sql": sql,
        "python": python,
        "chart_type": chart_type,
        "answer": answer,
        "reasoning": reasoning,
    }
