"""Compare ablation arms.

The default run is offline: schema-filter size, SQL safety, and gold-query health.
It does not call NVIDIA and it does not load a local model. Pass --live only after
the free API key is set. Live EX is left blank in the offline report on purpose;
the sample numbers in the build guide are illustrations, not this warehouse.
"""

from __future__ import annotations

import argparse
import json

from backend.agent.arms import ARMS
from backend.config import PROJECT_ROOT, get_settings
from backend.db.golden import GOLDEN_CASES
from backend.db.seed import seed_database
from backend.schema.context import build_schema_context
from backend.security.sql_guard import review_sql
from backend.system_check import collect_host_status, heavy_work_allowed
from backend.tools.sql_tool import run_select
from eval.harness import score

ADVERSARIAL = [
    "DELETE FROM customers",
    "DROP TABLE orders",
    "UPDATE customers SET name = 'x'",
    "INSERT INTO customers (customer_id) VALUES (1)",
    "SELECT 1; DROP TABLE orders",
    "PRAGMA writable_schema = ON",
    "ATTACH DATABASE 'evil.db' AS evil",
    "/* harmless */ DELETE FROM orders",
]

RESULTS = PROJECT_ROOT / "eval" / "results" / "ablation_latest.json"


def offline_report() -> dict:
    reductions = []
    for case in GOLDEN_CASES:
        full, _full_names = build_schema_context(case["question"], filter_schema=False, mode="full")
        filtered, _names = build_schema_context(case["question"], filter_schema=True, mode="full")
        if full:
            reductions.append(1 - (len(filtered) / len(full)))
    gold_ok = 0
    gold_times = []
    for case in GOLDEN_CASES:
        decision = review_sql(case["sql"])
        result = run_select(case["sql"])
        if decision.allowed and result["ok"]:
            gold_ok += 1
            gold_times.append(result["elapsed_s"])
    blocked = sum(1 for sample in ADVERSARIAL if not review_sql(sample).allowed)
    return {
        "golden_sql_passing": gold_ok,
        "golden_sql_total": len(GOLDEN_CASES),
        "mean_gold_latency_s": round(sum(gold_times) / len(gold_times), 4) if gold_times else None,
        "adversarial_blocked": blocked,
        "adversarial_total": len(ADVERSARIAL),
        "safe_sql_rate": round(blocked / len(ADVERSARIAL), 4),
        "mean_schema_chars_removed": round(sum(reductions) / len(reductions), 4) if reductions else 0,
    }


def live_report(arms: list[str], limit: int) -> list[dict]:
    rows = []
    for name in arms:
        if name not in ARMS:
            continue
        summary = score(demo=False, limit=limit, arm=name)
        rows.append(
            {
                "arm": name,
                "title": ARMS[name].title,
                "execution_accuracy": summary["execution_accuracy"],
                "ves": summary["mean_ves"],
                "safe_sql_rate": summary["safe_sql_rate"],
                "avg_latency_s": round(summary["elapsed_s"] / max(summary["cases"], 1), 3),
                "avg_tokens": summary["avg_tokens"],
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ablation study")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--arms", default="A,B,C")
    args = parser.parse_args(argv)

    allowed, reason = heavy_work_allowed()
    host = collect_host_status()
    print(reason)
    ram = host["memory"].get("total_gb")
    ram_text = f"{ram} GB" if ram else "unavailable"
    print(
        f"GPU available: {host['gpu']['available']}. "
        f"RAM: {ram_text}. Local training: disabled."
    )
    if not allowed:
        print("Stopping. GPU utilization is too high for extra local work.")
        return 2

    seed_database(reset=False)
    report = {"host": host, "offline": offline_report(), "live": None}
    offline = report["offline"]
    print(
        f"Offline: {offline['golden_sql_passing']}/{offline['golden_sql_total']} gold queries ran, "
        f"safe SQL {offline['safe_sql_rate'] * 100:.0f}% on adversarial probes, "
        f"schema filter removed {offline['mean_schema_chars_removed'] * 100:.1f}% of prompt characters on average."
    )
    print("EX / VES / tokens stay blank until you run --live with a free NVIDIA_API_KEY.")
    print(f"{'Arm':<8}{'EX':>8}{'VES':>8}{'Safe':>8}{'Latency':>10}{'Tokens':>10}")
    for name in [part.strip() for part in args.arms.split(",") if part.strip()]:
        title = ARMS.get(name)
        if title is None:
            continue
        print(f"{name:<8}{'—':>8}{'—':>8}{'—':>8}{'—':>10}{'—':>10}  {title.title}")

    if args.live:
        if not get_settings().nvidia_configured:
            print("NVIDIA_API_KEY is empty. Live arms were not called.")
            return 2
        names = [part.strip() for part in args.arms.split(",") if part.strip()]
        report["live"] = live_report(names, args.limit)
        print(f"\nLive, first {args.limit} golden questions:")
        print(f"{'Arm':<8}{'EX':>8}{'VES':>8}{'Safe':>8}{'Latency':>10}{'Tokens':>10}")
        for row in report["live"]:
            print(
                f"{row['arm']:<8}{row['execution_accuracy'] * 100:>7.1f}%"
                f"{row['ves']:>8.3f}{row['safe_sql_rate'] * 100:>7.0f}%"
                f"{row['avg_latency_s']:>10.2f}{row['avg_tokens']:>10.0f}"
            )

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
