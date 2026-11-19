"""Fail when docs/CONFIG.md and the dataclasses drift apart."""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from riskpilot.config import AppConfig
from riskpilot.guard import GuardConfig
from riskpilot.instruments import InstrumentSpec

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DOC = ROOT / "docs" / "CONFIG.md"
ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")


def documented_keys() -> dict[str, set[str]]:
    """Split documented keys by the table they appear in."""
    sections: dict[str, set[str]] = {"app": set(), "guard": set(), "instruments": set()}
    current = None
    for line in CONFIG_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if "load_config" in line:
                current = "app"
            elif "[guard]" in line:
                current = "guard"
            elif "load_instruments" in line:
                current = "instruments"
            else:
                current = None
            continue
        match = ROW.match(line)
        if match and current is not None:
            sections[current].add(match.group(1))
    return sections


def test_app_config_keys_documented() -> None:
    documented = documented_keys()["app"]
    expected = {f.name for f in fields(AppConfig)}
    assert expected <= documented, f"missing from docs/CONFIG.md: {sorted(expected - documented)}"
    assert documented <= expected | {"guard"}, (
        f"documented but not a dataclass field: {sorted(documented - expected)}"
    )


def test_guard_keys_documented() -> None:
    documented = documented_keys()["guard"]
    expected = {f.name for f in fields(GuardConfig)}
    assert expected <= documented, f"missing from docs/CONFIG.md: {sorted(expected - documented)}"
    assert documented <= expected, f"documented but not a field: {sorted(documented - expected)}"


def test_instrument_keys_documented() -> None:
    documented = documented_keys()["instruments"]
    expected = {f.name for f in fields(InstrumentSpec)} - {"symbol"}
    assert expected <= documented
    assert documented <= expected, f"documented but not a field: {sorted(documented - expected)}"


def config_rows() -> list[str]:
    """Return only the table rows that define a configuration key."""
    rows: list[str] = []
    current = None
    for line in CONFIG_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if "load_config" in line:
                current = "app"
            elif "[guard]" in line:
                current = "guard"
            elif "load_instruments" in line:
                current = "instruments"
            else:
                current = None
            continue
        if current is not None and ROW.match(line):
            rows.append(line)
    return rows


def test_every_key_row_mentions_a_type_and_range() -> None:
    rows = config_rows()
    assert rows
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 4, row
        assert cells[1], f"missing type in row: {row}"
        assert cells[2], f"missing default in row: {row}"
        assert cells[3], f"missing range in row: {row}"


def test_required_docs_exist_and_are_non_empty() -> None:
    for name in ("ARCHITECTURE.md", "CONFIG.md", "DECISIONS.md"):
        path = ROOT / "docs" / name
        assert path.is_file(), f"missing docs/{name}"
        assert len(path.read_text(encoding="utf-8").strip()) > 200
    changelog = ROOT / "CHANGELOG.md"
    assert changelog.is_file()
    text = changelog.read_text(encoding="utf-8")
    assert "Keep a Changelog" in text
    assert "## [Unreleased]" in text
    assert re.search(r"^## \[\d+\.\d+\.\d+\]", text, flags=re.MULTILINE)
