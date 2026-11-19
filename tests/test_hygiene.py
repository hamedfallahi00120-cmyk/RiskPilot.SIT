"""Repository hygiene rules that must hold for every commit."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".toml", ".md", ".yml", ".yaml", ".cfg", ".txt", ".csv", ".editorconfig"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".arena",
    ".egg-info",
    "node_modules",
}
MAX_FILE_LINES = 400
#: Total budget of suppression comments in ``src/`` (each must be justified).
SUPPRESSION_BUDGET = 3
SUPPRESSIONS = re.compile(r"#\s*(?:type:\s*ignore|noqa)", re.IGNORECASE)
#: Built character by character so that this module does not contain the
#: literals it forbids (the rule applies to the rule itself).
WORK_MARKERS = ("T" + "ODO", "FIX" + "ME", "X" * 3, "HA" + "CK")
JUSTIFIED = re.compile(r"#\s*(?:type:\s*ignore\[[^\]]+\]|noqa:\s*\S+)\s+-\s+\S+")


def text_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if SKIP_DIRS & set(relative.parts) or any(
            part.endswith(".egg-info") for part in relative.parts
        ):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name == ".editorconfig":
            files.append(path)
    return files


def owned_text_files() -> list[Path]:
    """Source, tests, docs, examples and config - the files this project owns."""
    prefixes = ("src/", "tests/", "docs/", "examples/")
    names = {
        "README.md",
        "CHANGELOG.md",
        "pyproject.toml",
        ".gitignore",
        ".editorconfig",
    }
    result = []
    for path in text_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(prefixes) or relative in names:
            result.append(path)
    return result


def test_text_files_found() -> None:
    assert len(owned_text_files()) >= 15


@pytest.mark.parametrize("path", owned_text_files(), ids=lambda p: p.name)
def test_final_newline_and_lf(path: Path) -> None:
    data = path.read_bytes()
    assert data.endswith(b"\n"), f"{path} must end with a final newline"
    assert b"\r\n" not in data, f"{path} must use LF line endings"
    assert b"\t" not in data or path.name == ".editorconfig", f"{path} must not use tabs"


@pytest.mark.parametrize("path", owned_text_files(), ids=lambda p: p.name)
def test_no_todo_or_fixme_markers(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in WORK_MARKERS:
        assert marker not in text, f"{path} contains {marker}"


@pytest.mark.parametrize("path", owned_text_files(), ids=lambda p: p.name)
def test_no_debug_prints(path: Path) -> None:
    if path.suffix != ".py" or path.name == "cli.py":
        return
    forbidden = "print" + "("
    assert forbidden not in path.read_text(encoding="utf-8"), f"{path} must not print"


@pytest.mark.parametrize("path", owned_text_files(), ids=lambda p: p.name)
def test_no_commented_out_code(path: Path) -> None:
    if path.suffix != ".py":
        return
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") and re.match(
            r"#\s*(?:from|import|def|class|return)\b", stripped
        ):
            pytest.fail(f"{path}:{number} looks like commented-out code: {stripped}")


@pytest.mark.parametrize("path", owned_text_files(), ids=lambda p: p.name)
def test_no_file_is_longer_than_400_lines(path: Path) -> None:
    count = len(path.read_text(encoding="utf-8").splitlines())
    assert count <= MAX_FILE_LINES, f"{path} has {count} lines"


def test_suppression_budget() -> None:
    found = []
    for path in (ROOT / "src").rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if SUPPRESSIONS.search(line):
                found.append(f"{path.relative_to(ROOT)}:{number}")
                assert JUSTIFIED.search(line), (
                    f"{path.relative_to(ROOT)}:{number} needs a written justification "
                    "('- <reason>') after the suppression comment"
                )
    assert len(found) <= SUPPRESSION_BUDGET, f"{found} exceeds the suppression budget"


def test_no_committed_artifacts() -> None:
    """No cache, bytecode or coverage file is tracked by git."""
    forbidden = (
        ".coverage",
        ".pyc",
        ".pyo",
        ".egg-info",
        ".pytest_cache",
        "htmlcov",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
    )
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line]
    assert tracked, "git ls-files returned nothing"
    offences = [
        name for name in tracked if any(part.endswith(forbidden) for part in Path(name).parts)
    ]
    assert not offences, f"committed artifacts: {offences}"


def test_gitignore_and_editorconfig_exist() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in gitignore
    assert ".coverage" in gitignore
    editorconfig = (ROOT / ".editorconfig").read_text(encoding="utf-8")
    assert "end_of_line = lf" in editorconfig
    assert "insert_final_newline = true" in editorconfig


def test_no_binary_artifacts_in_package() -> None:
    for path in (ROOT / "src").rglob("*"):
        assert path.suffix not in {".mp4", ".zip", ".srt"}, f"{path} must not be shipped"


def test_ci_workflow_exists() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "3.11" in text and "3.12" in text and "3.13" in text
    assert "permissions:" in text and "contents: read" in text
    assert "cache: pip" in text
    assert "ruff check" in text
    assert "ruff format --check" in text
    assert "mypy" in text
    assert "pytest" in text


def test_license_file_is_absent_by_decision() -> None:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        assert not (ROOT / name).exists(), "no LICENSE file is shipped, by the owner's decision"
