"""Ablation arms. G is the production configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Arm:
    name: str
    title: str
    use_sql: bool
    use_python: bool
    schema_filter: bool
    guidance: bool
    chart_agent: bool
    context_mode: str


ARMS: dict[str, Arm] = {
    "A": Arm("A", "Baseline, no tools", False, False, False, False, False, "full"),
    "B": Arm("B", "SQL tool", True, False, False, False, False, "full"),
    "C": Arm("C", "Python sandbox, no SQL", False, True, False, False, False, "full"),
    "D": Arm("D", "SQL plus schema filter", True, False, True, False, False, "full"),
    "E": Arm("E", "SQL, filter, and profiling", True, False, True, True, False, "full"),
    "F": Arm("F", "Chart review added", True, True, True, True, True, "full"),
    "G": Arm("G", "Full agent", True, True, True, True, True, "full"),
    "H": Arm("H", "Semantic notes only", True, True, True, True, True, "semantic"),
    "I": Arm("I", "Semantic notes via tool", True, True, True, True, True, "tool"),
    "J": Arm("J", "Prefer precomputed views", True, True, True, True, True, "views"),
}


def apply_arm_policy(plan: dict, arm_name: str) -> dict:
    arm = ARMS.get(arm_name, ARMS["G"])
    updated = dict(plan)
    if updated.get("next_step") == "fetch_context":
        return updated
    if not arm.use_sql:
        updated["sql"] = None
    if not arm.use_python:
        updated["python"] = None
        updated["chart_type"] = "none"
    if not arm.use_sql and not arm.use_python:
        updated["next_step"] = "respond"
        updated["sql"] = None
        updated["python"] = None
        updated["chart_type"] = "none"
        if not updated.get("answer"):
            updated["answer"] = (
                "This configuration has no database or Python tools, so nothing was executed."
            )
        return updated
    step = updated.get("next_step")
    has_sql = bool(updated.get("sql"))
    has_python = bool(updated.get("python"))
    if step == "both":
        if has_sql and has_python:
            updated["next_step"] = "both"
        elif has_sql:
            updated["next_step"] = "execute_sql"
        elif has_python:
            updated["next_step"] = "run_python"
        else:
            updated["next_step"] = "respond"
    elif step == "execute_sql" and not has_sql:
        updated["next_step"] = "respond"
    elif step == "run_python" and not has_python:
        updated["next_step"] = "respond"
    return updated


def arm_clause(arm: Arm) -> str:
    parts = []
    parts.append("execute_sql is available." if arm.use_sql else "execute_sql is disabled. Do not write SQL.")
    parts.append("run_python is available." if arm.use_python else "run_python is disabled. Do not write Python.")
    if arm.context_mode == "tool":
        parts.append("Call fetch_context before any other tool.")
    if not arm.use_sql and not arm.use_python:
        parts.append("No tools are available. Say that the database was not queried.")
    return " ".join(parts)
