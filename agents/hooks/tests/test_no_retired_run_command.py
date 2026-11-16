"""`run_command` was retired on 2026-11-16; omp's native `bash` (extended by bash-rules) replaced it.

Agent prompts, the always-on instructions, and the steer hooks are what an agent reads at
run time. A prompt that still tells an agent to use `run_command` sent a worker into a
"tool unavailable" dead end and made it report its runtime checks as blocked. These tests
pin the places that decide what an agent is told, so the retired name cannot return as an
instruction.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
MASTERS = sorted((REPO / "agents" / "agents").glob("*.yaml"))
INSTRUCTION_FILES = (
    REPO / "agents" / "AGENTS.md",
    REPO / "agents" / "learnings" / "pm-agent-prompt.md",
    REPO / "agents" / "hooks" / "bash-tool-steer.py",
    REPO / "agents" / "hooks" / "shell-denial-steer.py",
    REPO / "agents" / "hooks" / "eval-sleep-guard.py",
    REPO / "agents" / "hooks" / "search-scope-guard.py",
    REPO / "agents" / "hooks" / "scope-guard-directives.yaml",
)

# A sentence that names the retired tool in order to say it is retired is the fix, not the bug.
RETIREMENT_NOTE = re.compile(
    r"retired|superseded|replaced|stale|former|no longer", re.IGNORECASE
)


def _stale_lines(path: Path) -> list[str]:
    return [
        f"{path.relative_to(REPO)}:{number}: {line.strip()[:120]}"
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if "run_command" in line and not RETIREMENT_NOTE.search(line)
    ]


@pytest.mark.parametrize("master", MASTERS, ids=lambda path: path.stem)
def test_master_does_not_list_run_command_as_a_capability(master: Path) -> None:
    tools = yaml.safe_load(master.read_text()).get("tools", {})
    listed = [*tools.get("always", []), *tools.get("searchable", [])]
    assert "run_command" not in listed, (
        f"{master.name} still grants the retired run_command capability"
    )
    assert "bash" in listed or tools.get("all"), f"{master.name} grants no shell"


@pytest.mark.parametrize("master", MASTERS, ids=lambda path: path.stem)
def test_master_prompt_does_not_instruct_run_command(master: Path) -> None:
    assert _stale_lines(master) == []


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=lambda path: path.name)
def test_instruction_file_does_not_instruct_run_command(path: Path) -> None:
    assert _stale_lines(path) == []
