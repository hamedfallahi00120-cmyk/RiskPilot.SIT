"""Meta tests that enforce project-wide invariants (H5, H6, H8)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from riskpilot import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "riskpilot"

# Layer index: an importer at layer N may only import modules at layer <= N.
# errors/_decimal/_version/_session are leaves (0); cli is the top (4).
# Core modules must never import cli.
_LAYERS = {
    "errors": 0,
    "_decimal": 0,
    "_version": 0,
    "_session": 0,
    "instruments": 1,
    "sizing": 2,
    "guard": 2,
    "config": 3,
    "cli": 4,
}


def _iter_sources() -> list[Path]:
    return sorted(SRC.glob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _riskpilot_leaf(module: str) -> str | None:
    if module == "riskpilot":
        return "__init__"
    if module.startswith("riskpilot."):
        return module.split(".", 1)[1]
    return None


def test_import_direction_is_respected() -> None:
    for path in _iter_sources():
        importer = path.stem
        if importer not in _LAYERS:
            continue
        for module in _imported_modules(path):
            leaf = _riskpilot_leaf(module)
            if leaf is None or leaf == "__init__":
                continue
            assert leaf in _LAYERS, f"unknown layer for {module!r} imported by {path.name}"
            assert _LAYERS[leaf] <= _LAYERS[importer], (
                f"{path.name} (layer {_LAYERS[importer]}) must not import {module!r} "
                f"(layer {_LAYERS[leaf]}): import direction is cli -> core -> errors"
            )


def test_core_never_imports_cli() -> None:
    for path in _iter_sources():
        if path.stem == "cli":
            continue
        assert "riskpilot.cli" not in _imported_modules(path)


def test_no_core_module_imports_io_or_printing() -> None:
    forbidden = {"print", "input", "open"}
    for path in _iter_sources():
        if path.stem in {"cli", "config"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden:
                raise AssertionError(f"{path.name} uses forbidden builtin {node.id!r}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{path.name} calls {node.func.id!r}"


def test_version_matches_pyproject() -> None:
    document = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == document["project"]["version"]


def test_version_string_not_duplicated_in_source() -> None:
    declared = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    pattern = re.compile(rf'["\']{re.escape(declared)}["\']')
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _iter_sources()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"version string {declared!r} duplicated in {offenders}"


def test_type_ignore_and_noqa_budget() -> None:
    """H6: at most three suppression comments across src, each justified."""
    suppressions: list[tuple[str, int, str]] = []
    pattern = re.compile(r"#\s*(type:\s*ignore|noqa)\b(.*)")
    for path in _iter_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = pattern.search(line)
            if match:
                suppressions.append((path.name, number, line.strip()))
    assert len(suppressions) <= 3, f"too many suppressions: {suppressions}"
    for name, _, line in suppressions:
        assert " - " in line or ":" in line.split("noqa")[-1], (
            f"suppression without justification in {name}: {line}"
        )


def test_no_todo_or_fixme_markers() -> None:
    pattern = re.compile(r"\b(TO" + r"DO|FIX" + r"ME|XX" + r"X)\b")
    for path in list(SRC.glob("*.py")) + list((REPO_ROOT / "tests").glob("*.py")):
        assert not pattern.search(path.read_text(encoding="utf-8")), f"marker found in {path.name}"


def test_no_file_exceeds_400_lines() -> None:
    for path in _iter_sources():
        count = len(path.read_text(encoding="utf-8").splitlines())
        assert count <= 400, f"{path.name} has {count} lines (> 400)"
