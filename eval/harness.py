"""Score the Golden 50.

--demo replays curated SQL and should score perfectly; it is a plumbing check.
--live calls NVIDIA and is the model score. It does not run unless you pass the flag.
"""

from __future__ import annotations

import argparse
import time

from backend.agent.runner import run_agent
from backend.config import get_settings
from backend.db.golden import GOLDEN_CASES
from backend.db.seed import seed_database
from backend.security.sql_guard import review_sql
from backend.tools.sql_tool import run_select
from eval.metrics import rows_equal, valid_efficiency_score


def score(demo: bool, limit: int | None, arm: str) -> dict:
    settings = get_settings()
    if not demo and not settings.nvidia_configured:
        raise SystemExit(
            "NVIDIA_API_KEY is empty, so live scoring was not started. "
            "Use --demo to check the harness, or add a free key and rerun with --live."
        )
    cases = GOLDEN_CASES[:limit] if limit else list(GOLDEN_CASES)
    mode = "scripted" if demo else "auto"
    correct = 0
    ves_total = 0.0
    safe = 0
    tokens = 0
    started = time.perf_counter()
    for case in cases:
        result = run_agent(case["question"], planner_mode=mode, arm=arm)
        gold = run_select(case["sql"])
        match = bool(result.get("sql")) and rows_equal(result.get("rows"), gold.get("rows"), ordered=case["ordered"])
        correct += int(match)
        predicted = float(result.get("sql_elapsed_s") or 0.001)
        ves_total += valid_efficiency_score(match, float(gold.get("elapsed_s") or 0.001), predicted)
        tokens += int(result.get("tokens") or 0)
        if result.get("blocked") or not result.get("sql") or review_sql(result["sql"]).allowed:
            safe += 1
    total = len(cases)
    return {
        "planner": mode,
        "arm": arm,
        "cases": total,
        "execution_accuracy": round(correct / total, 4) if total else 0,
        "mean_ves": round(ves_total / total, 4) if total else 0,
        "safe_sql_rate": round(safe / total, 4) if total else 1,
        "avg_tokens": round(tokens / total, 1) if total else 0,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the Golden 50")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--arm", default="G")
    args = parser.parse_args(argv)
    if args.demo == args.live:
        print("Choose one of --demo (no API) or --live (NVIDIA, key required).")
        return 2
    seed_database(reset=False)
    summary = score(demo=args.demo, limit=args.limit or None, arm=args.arm)
    print(
        f"{summary['planner']} arm {summary['arm']}: "
        f"EX {summary['execution_accuracy'] * 100:.1f}%  "
        f"VES {summary['mean_ves']:.3f}  "
        f"safe {summary['safe_sql_rate'] * 100:.1f}%  "
        f"({summary['cases']} cases, {summary['elapsed_s']}s)"
    )
    if args.demo:
        print("Demo mode replays curated SQL. Use --live after adding NVIDIA_API_KEY for a model score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
