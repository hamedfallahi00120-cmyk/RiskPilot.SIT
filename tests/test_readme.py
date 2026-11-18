"""Execute the README console examples and compare output byte-for-byte."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from riskpilot.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"


def _console_blocks() -> list[tuple[str, str]]:
    """Return (command, expected_stdout) for each ````console`` README block."""
    text = README.read_text(encoding="utf-8")
    blocks: list[tuple[str, str]] = []
    parts = text.split("```console\n")
    for part in parts[1:]:
        body, _, _ = part.partition("```")
        lines = body.splitlines()
        command = lines[0]
        assert command.startswith("$ "), f"unexpected console block: {command!r}"
        expected = "\n".join(lines[1:])
        blocks.append((command[2:], expected))
    return blocks


def test_readme_has_console_blocks() -> None:
    assert len(_console_blocks()) >= 4


@pytest.mark.parametrize("command,expected", _console_blocks())
def test_readme_console_block(
    command: str, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = shlex.split(command)
    assert argv[0] == "riskpilot"
    code = main(argv[1:])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.rstrip("\n") == expected
