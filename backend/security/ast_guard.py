"""Static check for analyst Python before it is allowed to start a process."""

from __future__ import annotations

import ast

ALLOWED_IMPORT_ROOTS = {
    "pandas",
    "numpy",
    "matplotlib",
    "math",
    "statistics",
    "datetime",
    "json",
    "csv",
    "collections",
    "itertools",
    "re",
    "functools",
    "decimal",
    "warnings",
    "textwrap",
    "calendar",
    "time",
    "io",
    "operator",
    "numbers",
    "bisect",
    "heapq",
    "array",
    "string",
    "pprint",
    "copy",
    "dataclasses",
    "enum",
    "typing",
}

BANNED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "vars",
    "locals",
}

BANNED_NAMES = {
    "__builtins__",
    "__loader__",
    "__spec__",
    "breakpoint",
    "eval",
    "exec",
    "compile",
    "__import__",
}

MAX_CODE_CHARS = 20_000


def check_python(code: str) -> list[str]:
    source = code or ""
    if not source.strip():
        return ["Python code is empty."]
    if len(source) > MAX_CODE_CHARS:
        return [f"Python code exceeds {MAX_CODE_CHARS} characters."]
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"Python syntax error: {exc.msg}"]
    visitor = _Guard()
    visitor.visit(tree)
    return visitor.errors


class _Guard(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and node.level > 0:
            self.errors.append("Relative imports are blocked.")
        elif node.module:
            self._check_module(node.module)
        else:
            self.errors.append("Import is missing a module name.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name in BANNED_CALLS:
            self.errors.append(f"Call blocked: {name}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__") and node.attr.endswith("__") and node.attr not in {"__name__"}:
            self.errors.append(f"Dunder access blocked: {node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in BANNED_NAMES:
            self.errors.append(f"Name blocked: {node.id}")
        self.generic_visit(node)

    def _check_module(self, module: str) -> None:
        root = module.split(".", 1)[0]
        if root not in ALLOWED_IMPORT_ROOTS:
            self.errors.append(f"Import blocked: {module}")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
