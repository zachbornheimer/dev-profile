"""The guard must start on any machine that shares ~/.agents, not just this Mac.

``scope-guard.py`` runs through a PATH-resolved ``python3`` — a fleet box's
``/usr/bin/python3`` may be an older, barer interpreter than ``lib`` needs
(3.10+, yaml), so the bootstrap re-execs through ``uv run --script`` (whose
env carries the PEP 723 requirements) and fails open when no capable start
exists. The shebang itself must name no one user's home directory.
"""

from __future__ import annotations

import stat
import sys
import venv
from pathlib import Path

from hook_harness import HOOKS_DIR, HookRunner

HOOK = HOOKS_DIR / "scope-guard.py"
SKIP_PAYLOAD = (
    '{"hook_event_name":"UserPromptSubmit","session_id":"x",'
    '"transcript_path":"","cwd":"/tmp","prompt":"x"}'
)
# The interpreter running this suite: 3.10+ with yaml, everywhere the suite runs.
CAPABLE_PYTHON_BIN = Path(sys.executable).parent


def write_stub_uv(directory: Path, body: str) -> Path:
    stub = directory / "uv"
    stub.write_text(body, encoding="utf-8")
    stub.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    return stub


def bare_interpreter_bin(tmp_path: Path) -> Path:
    """A fresh interpreter with no yaml, on any machine, from this suite's own.

    ``venv --without-pip`` gives the fleet's interpreter shape — capable
    version, no yaml — so the hook's lacks-yaml branch runs identically here
    and there. Its ``bin`` resolves ``python3`` first on the PATHs below.
    """
    bare = tmp_path / "bare"
    venv.create(bare, with_pip=False)
    return bare / "bin"


def test_the_shebang_names_a_path_resolved_interpreter() -> None:
    """No user's home directory may be baked into the hook's start."""
    shebang = HOOK.read_text(encoding="utf-8").splitlines()[0]
    assert shebang == "#!/usr/bin/env python3"
    assert "/Users/" not in shebang and "/home/" not in shebang


def test_a_bare_interpreter_re_execs_through_uv(
    tmp_path: Path, hooks: HookRunner
) -> None:
    """A python3 without yaml hands the hook to uv's script env."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    record = tmp_path / "uv-argv"
    stub_body = "#!/bin/sh\n"
    stub_body += 'printf "%s\\n" "$@" > "' + str(record) + '"\n'
    stub_body += "exit 0\n"
    write_stub_uv(stub_dir, stub_body)
    # The fresh no-yaml interpreter resolves first on PATH, so the hook's
    # lacks-yaml branch re-execs before any lib import.
    run = hooks.session(
        "bare-reexec",
        {"PATH": f"{bare_interpreter_bin(tmp_path)}:{stub_dir}:/usr/bin:/bin"},
    ).run_payload("scope-guard.py", SKIP_PAYLOAD)
    assert run.exit_code == 0, run.stderr
    argv = record.read_text(encoding="utf-8").splitlines()
    assert argv[0] == "run"
    assert argv[1] == "--script"
    assert argv[2] == str(HOOK)


def test_a_capable_interpreter_runs_the_hook_without_uv(
    tmp_path: Path, hooks: HookRunner
) -> None:
    """python3 with yaml is the fast path: no uv process may be spawned."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    # A stub that would poison the run proves it is never called.
    write_stub_uv(stub_dir, "#!/bin/sh\nexit 99\n")
    run = hooks.session(
        "capable", {"PATH": f"{stub_dir}:{CAPABLE_PYTHON_BIN}:/usr/bin:/bin"}
    ).run_payload("scope-guard.py", SKIP_PAYLOAD)
    assert run.exit_code == 0, run.stderr
    assert run.stdout == "", run.stdout


def test_a_missing_uv_fails_open_without_output(
    tmp_path: Path, hooks: HookRunner
) -> None:
    """A no-yaml interpreter and no uv: the hook allows, it never blocks."""
    # The fresh no-yaml interpreter resolves first, and no uv exists on PATH.
    run = hooks.session(
        "fail-open", {"PATH": f"{bare_interpreter_bin(tmp_path)}"}
    ).run_payload("scope-guard.py", SKIP_PAYLOAD)
    assert run.exit_code == 0, run.exit_code
    assert run.stdout == "", run.stdout
    assert "no capable interpreter start" in run.stderr
