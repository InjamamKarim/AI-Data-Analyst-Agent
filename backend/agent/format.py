"""Turn rows into a readable answer when the model is not asked to phrase one."""

from __future__ import annotations

from typing import Any


def markdown_table(rows: list[dict[str, Any]], limit: int = 20) -> str:
    if not rows:
        return "_No rows._"
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows[:limit]:
        cells = [_cell(row.get(column, "")) for column in columns]
        body.append("| " + " | ".join(cells) + " |")
    table = "\n".join([header, divider, *body])
    if len(rows) > limit:
        table += f"\n\n_Showing {limit} of {len(rows)} rows._"
    return table


def draft_answer(state: dict) -> str:
    if state.get("rejected"):
        return "This plan was not approved, so nothing ran."
    if state.get("blocked"):
        return state.get("error") or "BLOCKED: Destructive operations are not permitted."
    if state.get("answer"):
        text = str(state["answer"])
    else:
        text = _from_rows(state)
    failures = int(state.get("python_failures") or 0)
    rows = ((state.get("sql_result") or {}).get("rows")) or []
    if failures >= 3 and rows and "failed three times" not in text:
        text += (
            "\n\nPython analysis failed three times, so the SQL result is shown as a table "
            "instead of a chart.\n\n" + markdown_table(rows)
        )
    return text.strip()


def _from_rows(state: dict) -> str:
    result = state.get("sql_result") or {}
    if result.get("blocked"):
        return result.get("error") or "BLOCKED: Destructive operations are not permitted."
    if result and not result.get("ok"):
        base = result.get("error") or "The query failed."
    else:
        base = ""
    rows = result.get("rows") or []
    parts = []
    if len(rows) == 1 and len(rows[0]) == 1:
        key, value = next(iter(rows[0].items()))
        parts.append(f"{key}: {value}")
    elif rows:
        parts.append(f"{len(rows)} row(s) returned.")
    elif result.get("ok"):
        parts.append("The query returned no rows.")
    elif not base:
        parts.append("No query was executed.")
    if base:
        parts.append(base)
    if rows:
        parts.append(markdown_table(rows))
    output = (state.get("python_output") or "").strip()
    if output:
        parts.append("Python output:\n" + output[:4000])
    if state.get("error") and not state.get("blocked") and state["error"] not in "\n".join(parts):
        parts.append("Note: " + str(state["error"]))
    return "\n\n".join(parts)


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
