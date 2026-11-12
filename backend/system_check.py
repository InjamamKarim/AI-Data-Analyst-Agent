"""Host probe used before any heavier local work.

This project does not download weights and does not train. The probe is here so
startup and the evaluation entrypoints record GPU and memory before they run.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from typing import Any


def probe_gpu() -> dict[str, Any]:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return {
            "available": False,
            "utilization_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "detail": "nvidia-smi is not available. No local NVIDIA GPU will be used.",
        }
    try:
        raw = subprocess.check_output(
            [
                binary,
                "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.SubprocessError, OSError) as exc:
        return {
            "available": False,
            "utilization_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "detail": f"nvidia-smi failed: {exc}",
        }
    first = raw.splitlines()[0] if raw else ""
    parts = [part.strip() for part in first.split(",")]
    util = _to_int(parts[0]) if len(parts) > 0 else None
    used = _to_int(parts[1]) if len(parts) > 1 else None
    total = _to_int(parts[2]) if len(parts) > 2 else None
    name = parts[3] if len(parts) > 3 else ""
    return {
        "available": True,
        "name": name,
        "utilization_percent": util,
        "memory_used_mb": used,
        "memory_total_mb": total,
        "detail": first,
    }


def probe_memory() -> dict[str, Any]:
    total = _memory_bytes()
    return {
        "total_bytes": total,
        "total_gb": round(total / (1024**3), 2) if total else None,
        "platform": platform.platform(),
    }


def collect_host_status() -> dict[str, Any]:
    gpu = probe_gpu()
    memory = probe_memory()
    return {
        "gpu": gpu,
        "memory": memory,
        "docker": bool(shutil.which("docker")),
        "heavy_local_workload": "disabled",
        "inference": "remote NVIDIA API only, and only after NVIDIA_API_KEY is set",
        "note": (
            "No weights are loaded on this machine and no training job exists. "
            "Python analysis runs one short subprocess at a time with a CPU limit."
        ),
    }


def heavy_work_allowed() -> tuple[bool, str]:
    """Gate for work that would actually load the GPU. Inference here is remote."""
    gpu = probe_gpu()
    if not gpu["available"]:
        return True, "No local NVIDIA GPU is present, and this app does not start local training."
    util = gpu.get("utilization_percent")
    if isinstance(util, int) and util >= 70:
        return (
            False,
            f"GPU utilization is {util}%. Refusing additional heavy local work until it drops.",
        )
    return True, "GPU utilization is below 70%. This app still does not train locally."


def _memory_bytes() -> int | None:
    try:
        if platform.system() == "Darwin":
            raw = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                text=True,
                timeout=3,
                stderr=subprocess.DEVNULL,
            ).strip()
            return int(raw)
        if platform.system() == "Linux":
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
    except (subprocess.SubprocessError, OSError, ValueError):
        pass
    if platform.system() != "Darwin":
        return None
    try:
        raw = subprocess.check_output(["memory_pressure"], text=True, timeout=3, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError):
        return None
    matched = re.search(r"The system has (\d+)", raw)
    if not matched:
        return None
    try:
        return int(matched.group(1))
    except ValueError:
        return None


def _to_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
