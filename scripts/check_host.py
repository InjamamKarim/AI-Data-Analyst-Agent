"""Print GPU and memory status. This project never starts local training."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.system_check import collect_host_status, heavy_work_allowed


def main() -> int:
    status = collect_host_status()
    allowed, reason = heavy_work_allowed()
    print(json.dumps({"host": status, "heavy_work_allowed": allowed, "reason": reason}, indent=2))
    print("Local model training and local weight loading are not part of this project.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
