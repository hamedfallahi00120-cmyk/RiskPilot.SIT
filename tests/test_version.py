"""Single source of truth for the version (pyproject.toml)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import riskpilot

ROOT = Path(__file__).resolve().parents[1]
#: Files allowed to mention the concrete version string (they *define* history).
VERSION_ALLOWED = {"pyproject.toml", "CHANGELOG.md", "README.md"}
TEXT_SUFFIXES = {".py", ".toml", ".yml", ".yaml", ".cfg", ".txt", ".srt", ".md"}
SKIP_DIRS = {".git", ".venv", "venv", "build", "dist", "__pycache__"}


def pyproject_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_runtime_version_matches_pyproject() -> None:
    assert riskpilot.__version__ == pyproject_version()


def test_version_has_no_duplicate_literal() -> None:
    version = pyproject_version()
    pattern = re.compile(rf"(?<![\w.]){re.escape(version)}(?![\w.])")
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(ROOT)
        if relative.as_posix() in VERSION_ALLOWED or SKIP_DIRS & set(relative.parts):
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(relative.as_posix())
    assert not offenders, f"version {version} is duplicated in {offenders}"


def test_init_reads_the_distribution_metadata() -> None:
    source = (ROOT / "src" / "riskpilot" / "__init__.py").read_text(encoding="utf-8")
    assert "importlib.metadata" in source
    assert "_distribution_version" in source
    assert not re.search(r"__version__\s*=\s*['\"]", source)
