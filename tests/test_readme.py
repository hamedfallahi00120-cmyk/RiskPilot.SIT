"""Execute the README's ``console`` examples and compare output byte for byte."""

from __future__ import annotations

import io
import shlex
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from riskpilot import __version__
from riskpilot.cli import main

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MARKER = "$ riskpilot"


def console_blocks() -> list[tuple[str, str]]:
    """Return ``(command, expected_output)`` pairs from every console block."""
    lines = README.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == "```console":
            index += 1
            body: list[str] = []
            while index < len(lines) and lines[index].strip() != "```":
                body.append(lines[index])
                index += 1
            assert index < len(lines), "unterminated console block in README"
            command_lines: list[str] = []
            output_lines: list[str] = []
            in_command = True
            for line in body:
                if in_command and line.startswith(MARKER):
                    command_lines.append(line[len(MARKER) :].strip())
                elif in_command and command_lines and line.startswith("    "):
                    command_lines.append(line.strip())
                else:
                    in_command = False
                    output_lines.append(line)
            if command_lines:
                blocks.append((" ".join(command_lines), "\n".join(output_lines).strip("\n")))
        index += 1
    return blocks


def run(command: str) -> tuple[int, str, str]:
    argv = shlex.split(command)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


BLOCKS = console_blocks()


def test_readme_has_executable_examples() -> None:
    assert len(BLOCKS) >= 4


def test_no_unexecuted_riskpilot_examples() -> None:
    """Every ``$ riskpilot`` line in the README must live in a console block."""
    text = README.read_text(encoding="utf-8")
    assert text.count(MARKER) == len(BLOCKS)


@pytest.mark.parametrize(("command", "expected"), BLOCKS, ids=[b[0] for b in BLOCKS])
def test_readme_example_matches_byte_for_byte(command: str, expected: str) -> None:
    code, out, err = run(command)
    if command.startswith("simulate"):
        # The simulate example is timestamped, so only its structure is checked.
        assert err == ""
        assert code == 3
        assert out.startswith("Generated at ")
        assert out.splitlines()[-3:] == [
            "final state: LOCKED",
            "final loss: 2000",
            "open positions: 0",
        ]
        return
    if command.startswith("--version"):
        expected = f"riskpilot-core {__version__}"
    assert err == ""
    assert code == 0
    assert out.rstrip("\n") == expected
