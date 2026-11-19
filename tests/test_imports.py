"""Enforce the import direction with ``ast`` (no import of riskpilot.cli in core)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "riskpilot"

#: Allowed intra-package edges: importer -> permitted targets.
ALLOWED: dict[str, set[str]] = {
    "__init__": {"errors", "guard", "instruments", "sizing"},
    "errors": set(),
    "_decimal": {"errors"},
    "_session": set(),
    "_guard_types": {"_decimal", "errors"},
    "instruments": {"_decimal", "errors"},
    "sizing": {"_decimal", "errors", "instruments"},
    "guard": {"_decimal", "_guard_types", "_session", "errors"},
    "config": {"errors", "guard", "instruments"},
    "cli": {"config", "errors", "guard", "instruments", "sizing", "__init__"},
}


def module_names() -> list[str]:
    return sorted(path.stem for path in SRC.glob("*.py"))


def imported_targets(path: Path) -> set[str]:
    """Return the set of intra-package module names imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("riskpilot."):
                    targets.add(alias.name.split(".")[1])
                elif alias.name == "riskpilot":
                    targets.add("__init__")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                msg = f"{path.name} uses a relative import; use absolute riskpilot imports"
                raise AssertionError(msg)
            module = node.module or ""
            if module == "riskpilot":
                targets.add("__init__")
                for alias in node.names:
                    targets.add(alias.name)
            elif module.startswith("riskpilot."):
                targets.add(module.split(".")[1])
    return targets


def test_every_module_is_covered_by_the_allowed_table() -> None:
    assert set(module_names()) == set(ALLOWED)


@pytest.mark.parametrize("module", module_names())
def test_import_direction(module: str) -> None:
    targets = imported_targets(SRC / f"{module}.py") & set(ALLOWED)
    forbidden = targets - ALLOWED[module]
    assert not forbidden, f"{module}.py must not import {sorted(forbidden)}"


@pytest.mark.parametrize(
    "module", ["errors", "instruments", "sizing", "guard", "config", "_guard_types"]
)
def test_core_never_imports_cli(module: str) -> None:
    source = (SRC / f"{module}.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "riskpilot.cli"
        if isinstance(node, ast.Import):
            assert all(alias.name != "riskpilot.cli" for alias in node.names)


def test_errors_is_a_leaf() -> None:
    assert imported_targets(SRC / "errors.py") == set()


def test_core_modules_are_pure() -> None:
    """The pure core must not print, read clocks, use randomness or open files."""
    banned_calls = {"print", "input", "open"}
    banned_modules = {"random", "secrets", "time", "pathlib", "os", "io", "sys"}
    for module in (
        "errors",
        "instruments",
        "sizing",
        "guard",
        "_decimal",
        "_session",
        "_guard_types",
    ):
        tree = ast.parse((SRC / f"{module}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, f"{module}.py calls {node.func.id}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned_modules, (
                        f"{module}.py imports {alias.name}"
                    )
            if isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in banned_modules, f"{module}.py imports from {node.module}"


def test_guard_never_reads_the_clock() -> None:
    tree = ast.parse((SRC / "guard.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"now", "utcnow", "today", "time"}, (
                "guard must not read the clock"
            )
