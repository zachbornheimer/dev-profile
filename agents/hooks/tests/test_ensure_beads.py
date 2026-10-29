"""ensure-beads.py: a git repo with no beads workspace gets one, in the background, once.

A fake ``bd`` on PATH stands in for the real tool: ``where`` succeeds when
the repo's main checkout has a ``.beads``; ``init`` records its argv and cwd.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from hook_harness import HookRunner, HookSession

HOOK = "ensure-beads.py"
INIT_RECORD = "init-record"
INIT_WAIT_SECS = 10
NO_INIT_SETTLE_SECS = 1.0
EXPECTED_INIT_ARGV = "init --quiet --stealth --skip-agents --skip-hooks --role maintainer --init-if-missing"
LOCK_PATH = ".git/ensure-beads.lock"

FAKE_BD = """#!/bin/sh
root=$(cd "$(git rev-parse --git-common-dir)/.." && pwd -P) || exit 1
case "$1" in
  where) [ -d "$root/.beads" ] ;;
  init) echo "$(pwd -P)|$*" > "$FAKE_BD_RECORD"; mkdir -p "$root/.beads" ;;
esac
"""


def _session_start(cwd: Path | str) -> dict:
    return {"cwd": str(cwd), "hook_event_name": "SessionStart"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
    )


def _make_repo(parent: Path, name: str = "repo") -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
    )
    return repo.resolve()


def _link(bin_dir: Path, program: str) -> None:
    found = shutil.which(program)
    assert found, program
    (bin_dir / program).symlink_to(found)


def _bin_dir(tmp_path: Path, *, with_bd: bool) -> Path:
    bin_dir = tmp_path / ("bin-bd" if with_bd else "bin-nobd")
    bin_dir.mkdir()
    for program in ("uv", "git"):
        _link(bin_dir, program)
    if with_bd:
        fake = bin_dir / "bd"
        fake.write_text(FAKE_BD)
        fake.chmod(0o755)
    return bin_dir


def _session(hooks: HookRunner, tmp_path: Path, *, with_bd: bool = True) -> HookSession:
    record = tmp_path / INIT_RECORD
    path = f"{_bin_dir(tmp_path, with_bd=with_bd)}:/usr/bin:/bin"
    return hooks.session(
        "ensure-beads",
        {"PATH": path, "FAKE_BD_RECORD": str(record), "HOME": str(tmp_path / "home")},
    )


def _init_record(tmp_path: Path, *, expect: bool) -> str | None:
    record = tmp_path / INIT_RECORD
    deadline = time.monotonic() + (INIT_WAIT_SECS if expect else NO_INIT_SETTLE_SECS)
    while time.monotonic() < deadline:
        if record.exists():
            return record.read_text().strip()
        time.sleep(0.1)
    return None


def _assert_clean(run) -> None:
    assert run.exit_code == 0
    assert run.stdout == ""
    assert not run.failed_open, run.log


def test_non_repo_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(plain))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_repo_without_beads_inits_at_repo_root_with_stealth_flags(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path)
    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(nested))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=True) == f"{repo}|{EXPECTED_INIT_ARGV}"


def test_repo_with_beads_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".beads").mkdir()
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(repo))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_worktree_of_repo_with_beads_is_a_no_op(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".beads").mkdir()
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "side", str(worktree))
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(worktree))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_worktree_without_beads_inits_at_the_main_checkout(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path)
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "side", str(worktree))
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(worktree))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=True) == f"{repo}|{EXPECTED_INIT_ARGV}"


def test_bare_repo_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(bare))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_gas_city_worktree_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "city" / ".gc" / "worktrees" / "rig")
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(repo))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_home_directory_repo_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    home = _make_repo(tmp_path, "home")
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(home))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_tmp_repo_is_a_no_op_by_default(hooks: HookRunner, tmp_path: Path) -> None:
    scratch = Path(tempfile.mkdtemp(dir="/tmp"))
    try:
        repo = _make_repo(scratch)
        run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(repo))

        _assert_clean(run)
        assert _init_record(tmp_path, expect=False) is None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_init_in_progress_blocks_a_second_init(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path)
    (repo / LOCK_PATH).write_text("")
    run = _session(hooks, tmp_path).run_payload(HOOK, _session_start(repo))

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None


def test_lock_is_released_after_init(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _session(hooks, tmp_path).run_payload(HOOK, _session_start(repo))

    assert _init_record(tmp_path, expect=True)
    deadline = time.monotonic() + INIT_WAIT_SECS
    while (repo / LOCK_PATH).exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not (repo / LOCK_PATH).exists()


def test_missing_bd_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    run = _session(hooks, tmp_path, with_bd=False).run_payload(
        HOOK, _session_start(repo)
    )

    _assert_clean(run)
    assert _init_record(tmp_path, expect=False) is None
    assert not (repo / LOCK_PATH).exists()


def test_missing_cwd_is_a_no_op(hooks: HookRunner, tmp_path: Path) -> None:
    run = _session(hooks, tmp_path).run_payload(
        HOOK, {"hook_event_name": "SessionStart"}
    )

    _assert_clean(run)
