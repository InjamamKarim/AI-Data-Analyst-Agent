"""Public entry used by the evaluation tests and the CLI."""

from __future__ import annotations

from typing import Any

from backend.agent.service import Session


def run_agent(question: str, **kwargs: Any) -> dict[str, Any]:
    """Run one question on a fresh in-memory checkpoint.

    planner_mode="scripted" replays the Golden 50 and does not call NVIDIA.
    planner_mode="auto" calls NVIDIA only when NVIDIA_API_KEY is set.
    """
    return Session().ask(question, **kwargs)
