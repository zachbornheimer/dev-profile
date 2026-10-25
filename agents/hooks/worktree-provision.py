#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""WorktreeCreate — canonical-location agent worktrees via worktrunk (`wt`).

Claude Code may pre-create `worktree-<name>` under `.claude/worktrees/`
before this hook runs; those are adopted onto
`<repo-parent>/.worktrees/<repo>-<name>`. New worktrees are created with
`wt switch --create` (exact dest via --config-set worktree-path). Stdout
purity: the worktree path is the LAST non-empty line; everything else on
stderr.

Work-order target-repo routing, chezmoi re-root, and stray cleanup stay
here because the worktrunk plugin's WorktreeCreate only runs
`wt switch --create $name` in CLAUDE_PROJECT_DIR.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Clock, HookEvent, HookLog, HookSettings, read_stdin
from worktree_provision_git import GitFacade
from worktree_provision_tools import chezmoi_source_path, provision_dependencies
from worktree_provision_worktrunk import WorktrunkError, ensure_worktree, resolve_wt_bin
from worktree_target_queue import claim as claim_worktree_target

HOOK_NAME = "worktree-provision"
git = GitFacade()
DEFAULT_CHEZMOI_LIVE_ROOTS = (
    str(Path.home() / ".agents"),
    str(Path.home() / ".claude"),
)
DEFAULT_CHEZMOI_SOURCE_REPO = str(Path.home() / "Developer" / "Personal" / "dotfiles")
PROVISION_TIMEOUT_SECS_DEFAULT = 150.0
COMPILE_SCRIPT = Path(__file__).resolve().parent / "lib" / "work-order-compile.py"
TARGET_RESOLVE_TIMEOUT_SECS = 30


def fail(log: HookLog, message: str) -> None:
    log.record("error", message)
    print(f"{HOOK_NAME}: {message}", file=sys.stderr)
    sys.exit(1)


def path_is_chezmoi_target(candidate: str, env: dict[str, str]) -> bool:
    trimmed = candidate.rstrip("/")
    roots_env = env.get("WORKTREE_CHEZMOI_LIVE_ROOTS")
    roots = roots_env.split(":") if roots_env else list(DEFAULT_CHEZMOI_LIVE_ROOTS)
    for root in roots:
        root = root.rstrip("/")
        if not root:
            continue
        if trimmed == root or trimmed.startswith(root + "/"):
            return True
    return False


def chezmoi_source_repo(env: dict[str, str]) -> str | None:
    override = env.get("CHEZMOI_SOURCE_REPO")
    if override:
        return git.show_toplevel(override)
    candidate = chezmoi_source_path() or DEFAULT_CHEZMOI_SOURCE_REPO
    return git.show_toplevel(candidate)


def base_ref_mode_from_settings() -> str:
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        data = json.loads(settings_path.read_text())
        mode = data.get("worktree", {}).get("baseRef")
        return mode if isinstance(mode, str) and mode else "fresh"
    except (OSError, ValueError, AttributeError):
        return "fresh"


def canonical_dest(repo_root: str, repo_name: str, name: str) -> str:
    marker = "/.worktrees/"
    if marker in repo_root:
        # nested worktree-of-worktree: land beside the outer repo, not
        # nested a second .worktrees/ dir under this one.
        outer = repo_root.split(marker, 1)[0]
        return f"{outer}/.worktrees/{repo_name}-{name}"
    return f"{Path(repo_root).parent}/.worktrees/{repo_name}-{name}"


def adopt_precreated_branch(repo_root: str, dest: str, branch: str, log: HookLog) -> bool:
    """True if a branch Claude Code already made was adopted onto dest."""
    if not git.branch_exists(repo_root, branch):
        return False
    existing = git.worktree_holding_branch(repo_root, branch)
    if existing == dest:
        log.record("adopt", f"{dest} branch={branch} mode=already-canonical")
        return True
    if existing:
        if git.relocate_worktree(repo_root, existing, dest):
            log.record("adopt", f"{dest} branch={branch} mode=moved from={existing}")
            return True
        fail(log, f"git worktree move failed from {existing} to {dest} (branch {branch})")
    if git.attach_worktree_to_branch(repo_root, dest, branch):
        log.record("adopt", f"{dest} branch={branch} mode=added-existing-branch")
        return True
    fail(log, f"git worktree add (adopt, no -b) failed for {dest} (branch {branch})")
    return False  # unreachable; fail() exits


def wt_base_for_mode(base_ref_mode: str) -> str:
    """wt --base shortcut: HEAD for 'head', default branch otherwise."""
    return "@" if base_ref_mode == "head" else "^"


def handle_non_repo_cwd(name: str, session_cwd: str, settings: HookSettings, log: HookLog) -> None:
    env = dict(os.environ)
    backing = None
    is_chezmoi_target = path_is_chezmoi_target(session_cwd, env)
    if is_chezmoi_target:
        backing = chezmoi_source_repo(env)
    if backing:
        repo_root = backing
        repo_name = Path(repo_root).name
        log.record("re-root", f"cwd={session_cwd} backing={backing}")
        print(
            f"{HOOK_NAME}: cwd is not a git repo; provisioning worktree from chezmoi source {backing}",
            file=sys.stderr,
        )
        provision_and_print(repo_root, repo_name, name, log)
        return
    if is_chezmoi_target:
        fail(
            log,
            f"cwd {session_cwd} is not a git repo and has no chezmoi backing repo. "
            f"Spawn with isolation none, or set cwd to {DEFAULT_CHEZMOI_SOURCE_REPO}.",
        )
        return
    dest = str(settings.state_dir / "bridge-worktrees" / name)
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError:
        fail(log, f"cannot create non-repo scratch dir {dest}")
        return
    log.record("create", f"{dest} scope=non-repo cwd={session_cwd}")
    print(dest)


def provision_and_print(repo_root: str, repo_name: str, name: str, log: HookLog) -> None:
    branch = f"worktree-{name}"
    base_ref_mode = base_ref_mode_from_settings()
    dest = canonical_dest(repo_root, repo_name, name)
    os.makedirs(str(Path(dest).parent), exist_ok=True)

    if adopt_precreated_branch(repo_root, dest, branch, log):
        provision_dependencies(repo_root, dest, _provision_timeout(), log)
        emit_worktree(dest, branch, log)
        return

    wt_bin = resolve_wt_bin()
    if not wt_bin:
        fail(log, "wt (worktrunk) is not on PATH")
        return
    try:
        switched = ensure_worktree(
            wt_bin,
            repo_root,
            branch,
            dest,
            wt_base_for_mode(base_ref_mode),
            timeout_secs=_provision_timeout(),
        )
    except WorktrunkError as exc:
        fail(log, f"wt switch failed for {dest} (branch {branch}): {exc}")
        return
    if switched.path != dest:
        if git.relocate_worktree(repo_root, switched.path, dest):
            log.record("adopt", f"{dest} branch={branch} mode=moved from={switched.path}")
        else:
            fail(
                log,
                f"wt created {switched.path} (branch {branch}) but relocate to {dest} failed",
            )
            return
    else:
        log.record(
            "create",
            f"{dest} branch={branch} base={wt_base_for_mode(base_ref_mode)} "
            f"created={switched.created}",
        )
    provision_dependencies(repo_root, dest, _provision_timeout(), log)
    emit_worktree(dest, branch, log)


def resolve_target_repo(record: str) -> str:
    """The queued order's target repo via work-order-compile.py target-repo."""
    try:
        proc = subprocess.run(
            [str(COMPILE_SCRIPT), "target-repo"],
            input=record,
            capture_output=True,
            text=True,
            timeout=TARGET_RESOLVE_TIMEOUT_SECS,
            check=False,
        )
        return str(json.loads(proc.stdout).get("target_repo") or "")
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return ""


def emit_worktree(path: str, branch: str, log: HookLog) -> None:
    """Mirror of emit_worktree in worktree-provision.sh: never hand the
    agent a worktree checked out on another branch."""
    on = git.current_branch(path)
    if on != branch:
        fail(
            log,
            f"worktree {path} is on branch '{on or '<none>'}', expected {branch}; refusing to hand it to the agent",
        )
    print(path)


def resolve_repo_root(
    event: HookEvent,
    session_repo: str | None,
    session_cwd: str,
    settings: HookSettings,
    log: HookLog,
) -> tuple[str, str]:
    """(repo_root, source): the work order's target repo when the gate
    queued one for this session, else the session cwd's repo."""
    fallback = session_repo or session_cwd
    record = claim_worktree_target(
        settings.state_dir, event.session_id, Clock.from_env().now_epoch()
    )
    if record is None:
        return fallback, "session-cwd"
    queued = resolve_target_repo(record)
    if not queued:
        return fallback, "work-order-no-repo-target"
    order_top = git.show_toplevel(queued)
    if order_top:
        return order_top, "work-order"
    log.record(
        "provision-warn", f"queued target {queued} is not a git work tree; using session cwd"
    )
    return fallback, "session-cwd"


def remove_stray_session_worktree(session_repo: str, branch: str, log: HookLog) -> None:
    """Claude Code pre-creates `branch` and a worktree under the SESSION
    repo's .claude/worktrees/ before this hook runs; when the order targets
    another repo that is litter. Never forced; the branch goes only if empty."""
    if not git.branch_exists(session_repo, branch):
        return
    stray = git.worktree_holding_branch(session_repo, branch)
    if stray:
        if not stray.startswith(f"{session_repo}/.claude/worktrees/"):
            log.record(
                "provision-warn",
                f"left {stray} (branch {branch}): not a Claude Code pre-created path",
            )
            return
        if not git.remove_worktree(session_repo, stray):
            log.record("provision-warn", f"left stray {stray} (worktree remove refused)")
            return
    if git.branch_is_empty(session_repo, branch) and git.delete_branch(session_repo, branch):
        log.record(
            "cleanup",
            f"removed stray {stray or '<no worktree>'} + branch {branch} from {session_repo}",
        )
    else:
        log.record(
            "provision-warn",
            f"kept branch {branch} in {session_repo} (has commits or delete failed)",
        )


def _provision_timeout() -> float:
    raw = os.environ.get("WORKTREE_PROVISION_TIMEOUT_SECS")
    try:
        return float(raw) if raw else PROVISION_TIMEOUT_SECS_DEFAULT
    except ValueError:
        return PROVISION_TIMEOUT_SECS_DEFAULT


def main() -> None:
    settings = HookSettings.from_env()
    log = HookLog(HOOK_NAME, settings, Clock.from_env())

    raw = read_stdin(settings.stdin_timeout_secs)
    if not raw:
        fail(log, "empty stdin")
        return

    event = HookEvent.parse(raw) or HookEvent({})
    name = event.field("name", "name")
    session_cwd = event.field("cwd", "cwd")
    if not name:
        fail(log, "missing 'name' field in WorktreeCreate input")
        return
    if not session_cwd:
        fail(log, "missing 'cwd' field in WorktreeCreate input")
        return

    session_repo = git.show_toplevel(session_cwd)
    repo_root, repo_source = resolve_repo_root(event, session_repo, session_cwd, settings, log)
    repo_name = Path(repo_root).name
    log.record(
        "repo",
        f"source={repo_source} repo={repo_root} name={name} session={event.session_id or '<none>'}",
    )
    if repo_source == "work-order" and session_repo and session_repo != repo_root:
        remove_stray_session_worktree(session_repo, f"worktree-{name}", log)

    if not git.is_inside_work_tree(repo_root):
        handle_non_repo_cwd(name, session_cwd, settings, log)
        return

    provision_and_print(repo_root, repo_name, name, log)


def main_failing_closed() -> None:
    """WorktreeCreate cannot fail open: without a path on stdout there is no
    worktree to hand back. An unexpected error therefore takes the same exit
    as every deliberate failure here — ``fail``'s one-line reason and exit 1,
    never a traceback — exactly like the .sh's ``fail``."""
    try:
        main()
    except Exception as exc:
        settings = HookSettings.from_env()
        fail(
            HookLog(HOOK_NAME, settings, Clock.from_env()),
            f"internal error: {type(exc).__name__}: {exc}",
        )


if __name__ == "__main__":
    main_failing_closed()
