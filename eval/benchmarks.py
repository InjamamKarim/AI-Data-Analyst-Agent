"""Hooks for external text-to-SQL suites.

BIRD and Spider 2.0 are not downloaded. They are large, and this machine is not
a place to unpack them automatically. Drop a local export in data/benchmarks
and call load_questions when you want to score it with eval.metrics.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.config import DATA_DIR

BIRD_DIR = DATA_DIR / "benchmarks" / "bird"
SPIDER_DIR = DATA_DIR / "benchmarks" / "spider2"


def load_questions(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is not on disk. This project does not download BIRD or Spider. "
            "Place a JSON list of {question, sql} objects there and rerun the harness."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must be a JSON list.")
    return payload


def bird_available() -> bool:
    return BIRD_DIR.exists()


def spider_available() -> bool:
    return SPIDER_DIR.exists()
