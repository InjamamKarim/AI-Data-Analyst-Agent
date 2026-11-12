"""Ask one question from the terminal."""

from __future__ import annotations

import argparse

from backend.agent.service import get_session
from backend.db.golden import GOLDEN_CASES
from backend.db.seed import seed_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the local data analyst agent")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--arm", default="G")
    parser.add_argument("--demo", action="store_true", help="Replay the Golden 50 instead of calling NVIDIA")
    parser.add_argument("--hitl", action="store_true")
    parser.add_argument("--examples", action="store_true")
    args = parser.parse_args(argv)
    seed_database(reset=False)
    if args.examples:
        for case in GOLDEN_CASES:
            print(f"{case['id']}: {case['question']}")
        return 0
    if not args.question:
        parser.error("Pass a question or --examples")
    mode = "scripted" if args.demo else "auto"
    result = get_session().ask(args.question, arm=args.arm, planner_mode=mode, hitl=args.hitl)
    print(result.get("output") or "")
    if result.get("sql"):
        print("\nSQL:\n" + result["sql"])
    if result.get("chart_path"):
        print("\nChart: " + result["chart_path"])
    if result.get("error") == "missing_api_key":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
