"""Chart checks used by the visualization node. No vision model is called."""

from __future__ import annotations

import re
from pathlib import Path

_PNG = b"\x89PNG\r\n\x1a\n"
_PATTERNS = {
    "bar": re.compile(r"plt\.barh?\s*\(|kind\s*=\s*['\"]barh?['\"]"),
    "line": re.compile(r"plt\.plot\s*\(|kind\s*=\s*['\"]line['\"]"),
    "pie": re.compile(r"plt\.pie\s*\(|kind\s*=\s*['\"]pie['\"]"),
    "scatter": re.compile(r"plt\.scatter\s*\(|kind\s*=\s*['\"]scatter['\"]"),
    "histogram": re.compile(r"plt\.hist\s*\(|kind\s*=\s*['\"]hist['\"]"),
}


def validate_chart(code: str | None, path: str | None, chart_type: str | None) -> tuple[bool, str]:
    kind = chart_type or "none"
    if kind == "none":
        return True, "No chart was requested."
    if kind not in _PATTERNS:
        return False, f"Unsupported chart type: {kind}"
    if not path:
        return False, "Chart file was not created."
    file = Path(path)
    if not file.is_file() or file.stat().st_size < 100:
        return False, "Chart file is missing or empty."
    if file.read_bytes()[:8] != _PNG:
        return False, "Chart file is not a PNG."
    if not _PATTERNS[kind].search(code or ""):
        return False, f"Python does not draw a {kind} chart."
    return True, "Chart looks usable."
