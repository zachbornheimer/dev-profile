#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# PreToolUse (Bash matcher) — shared main-checkout git guard.
#
# Incident (2026-08-26): a subagent ran `git commit` in a dirty
# ~/Developer/.../isjac main checkout; lefthook's hide-unstaged step
# reverted 78 uncommitted files. Subagents mutate git state ONLY inside a
# worktree (~/Developer/<Org>/.worktrees/...) per the orchestrator contract
# in ~/.claude/CLAUDE.md — they never touch a shared main checkout's git
# state, because a main checkout's working tree is shared with whatever the
# human (or another agent) is mid-edit on.
#
# Denies a state-mutating git subcommand (commit, add, stash push/save,
# reset, restore, checkout with a pathspec/--, update-index, clean, merge,
# rebase, cherry-pick, am, apply without --check) when the target repo:
#   - is NOT under a `/.worktrees/` path, and
#   - is NOT under the scratchpad/tmp scratch area, and
#   - is being touched from a subagent (agent_id present in hook input) —
#     OR, for the main session itself, the repo has unstaged tracked
#     modifications (`git status --porcelain` has a line starting " M"),
#     which is the same signal that predicts a lefthook hide-unstaged
#     revert.
#
# Read-only git (status, log, diff, show, ls-tree, rev-parse, fetch, stash
# list/show) and push are always allowed. ALLOW_MAIN_CHECKOUT_GIT=1 present
# in the command (as a literal env-assignment token) — or set in the
# process env — bypasses the guard: Zach's deliberate override.
#
# Fails OPEN on any parse error, missing git, or unexpected input: a false
# block is more costly than a missed check.
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import run_fail_open

STDIN_TIMEOUT_SECS = 5
HOOKS_LOG = Path.home() / ".claude" / "hooks" / "state" / "hooks.log"
HOOK_NAME = "shared-checkout-guard"
WORKTREE_HINT = "work in a git worktree (~/Developer/<Org>/.worktrees/...) or ask the orchestrator"

MUTATING_SUBCOMMANDS = {
    "commit",
    "add",
    "reset",
    "restore",
    "update-index",
    "clean",
    "merge",
    "rebase",
    "cherry-pick",
    "am",
}

CONTROL_OPERATORS = {"&&", "||", ";", "|"}


def log(decision: str, detail: str) -> None:
    """Append to the shared hooks.log in hook-common.sh's tab format."""
    try:
        HOOKS_LOG.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with HOOKS_LOG.open("a") as f:
            f.write(f"{now}\t{HOOK_NAME}\t{decision}\t{detail}\n")
    except Exception:
        pass


def read_stdin_json() -> dict:
    """Read+parse hook stdin JSON. Fails open (empty dict) on any error."""
    try:
        import select

        if not select.select([sys.stdin], [], [], STDIN_TIMEOUT_SECS)[0]:
            return {}
        raw = sys.stdin.read()
        if not raw:
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def field(payload: dict, snake: str, camel: str):
    """First non-empty of payload[snake] / payload[camel] — Grok camelCase
    compat, mirroring hook-common.sh's hc_field."""
    val = payload.get(snake)
    if val:
        return val
    return payload.get(camel)


def tool_name(payload: dict) -> str:
    name = payload.get("tool_name") or payload.get("toolName") or ""
    aliases = {
        "run_terminal_command": "Bash",
        "search_replace": "Edit",
        "write": "Write",
        "spawn_subagent": "Task",
    }
    return aliases.get(name, name)


def tool_input_field(payload: dict, key: str):
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    return tool_input.get(key)


def tokenize(cmd: str):
    """Shell-word-split, tolerant of unmatched quotes (falls back to a
    naive whitespace split, matching hook-common.sh's hc_tokenize
    fallback)."""
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return cmd.split()


def deny(reason: str) -> int:
    log("deny", reason)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def allow(detail: str) -> int:
    log("allow", detail)
    return 0


def find_git_invocation_indices(tokens):
    return [i for i, tok in enumerate(tokens) if tok == "git"]


def extract_repo_dir_and_subcommand(tokens, git_index):
    """Walks forward from a "git" token, capturing a `-C <path>` global
    flag if present, then the first non-flag token as the subcommand."""
    repo_dir = None
    subcmd = None
    i = git_index + 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "-C" and i + 1 < n:
            repo_dir = tokens[i + 1]
            i += 2
            continue
        if tok == "-c" and i + 1 < n:
            i += 2
            continue
        if tok.startswith("--git-dir="):
            i += 1
            continue
        if tok.startswith("-"):
            i += 1
            continue
        subcmd = tok
        break
    return repo_dir, subcmd


def checkout_is_mutating(tokens, checkout_index) -> bool:
    """True when the checkout invocation restores a pathspec (a literal
    "--" token, or 2+ non-flag tokens after "checkout") rather than a
    plain branch switch."""
    count = 0
    for tok in tokens[checkout_index + 1 :]:
        if tok in CONTROL_OPERATORS:
            break
        if tok == "--":
            return True
        if not tok.startswith("-"):
            count += 1
    return count >= 2


def stash_subcommand(tokens, git_index) -> str:
    """The stash verb after this git invocation, skipping global options."""
    i = git_index + 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in CONTROL_OPERATORS:
            return ""
        if tok == "-C" and i + 1 < n:
            i += 2
            continue
        if tok == "-c" and i + 1 < n:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if tok != "stash":
            return ""
        verb = tokens[i + 1] if i + 1 < n else ""
        if verb in CONTROL_OPERATORS or verb.startswith("-"):
            return ""
        return verb
    return ""


def stash_is_mutating(tokens, git_index) -> bool:
    """`stash list` and `stash show` are read-only; push, save, and bare stash mutate."""
    return stash_subcommand(tokens, git_index) not in ("list", "show")


def apply_is_mutating(tokens, apply_index) -> bool:
    """`git apply --check` is a dry-run; any other apply invocation
    mutates the working tree."""
    for tok in tokens[apply_index + 1 :]:
        if tok in CONTROL_OPERATORS:
            break
        if tok == "--check":
            return False
    return True


def invocation_is_mutating(tokens, git_index, subcmd) -> bool:
    if subcmd == "checkout":
        return checkout_is_mutating(tokens, git_index)
    if subcmd == "stash":
        return stash_is_mutating(tokens, git_index)
    if subcmd == "apply":
        return apply_is_mutating(tokens, git_index)
    return subcmd in MUTATING_SUBCOMMANDS


def path_is_worktree_or_scratch(path: str) -> bool:
    """True for a canonical <repo-parent>/.worktrees/... worktree (the
    placement worktree-provision.sh uses for every repo, regardless of
    where it's rooted), a per-repo Claude Code default worktree
    (<repo>/.claude/worktrees/<name> — the placement Claude Code's
    built-in flow would use absent a WorktreeCreate hook), or scratch
    space."""
    if not path:
        return False
    return (
        "/.worktrees/" in path
        or "/.claude/worktrees/" in path
        or path.startswith(("/tmp/", "/private/tmp/"))
        or "/scratchpad/" in path
    )


ASSIGNMENT_RE = __import__("re").compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
VAR_REF_RE = __import__("re").compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


def substitute_literal_vars(value: str, env_assignments: dict) -> str:
    """Best-effort $VAR / ${VAR} substitution using only literal
    assignments seen earlier in THIS command (or the hook's own process
    env as a fallback). Never executes anything. Returns the value
    unchanged (still containing '$') when a reference can't be resolved
    — callers treat a leftover '$' as "cwd became unknown"."""
    if "$(" in value or "`" in value:
        return value  # command substitution — cannot resolve statically

    def repl(m: "__import__('re').Match") -> str:
        name = m.group(1)
        if name in env_assignments:
            return env_assignments[name]
        return os.environ.get(name, m.group(0))

    return VAR_REF_RE.sub(repl, value)


def track_cwd_per_git_index(tokens, session_cwd: str) -> dict:
    """Single forward pass over the tokenized command: tracks literal
    `VAR=value` assignments and `cd <path>` occurrences so each "git"
    token index maps to the cwd actually in effect at that point in the
    script — not just the cwd the Bash tool started the whole command
    in. A `cd` whose target can't be statically resolved (a subshell,
    command substitution, or an unassigned/dynamic var) marks the cwd
    UNKNOWN (None) from that point on, so callers fall back to the old
    session_cwd behavior rather than trusting a guess."""
    cwd_at: dict = {}
    current_dir = session_cwd
    env_assignments: dict = {}
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        m = ASSIGNMENT_RE.match(tok)
        if m and tok not in ("cd",):
            env_assignments[m.group(1)] = substitute_literal_vars(m.group(2), env_assignments)
            i += 1
            continue
        if tok == "cd" and i + 1 < n:
            raw = tokens[i + 1]
            if raw == "-" or raw.startswith("-"):
                current_dir = None  # `cd -`/flag — don't guess
            else:
                resolved = substitute_literal_vars(raw, env_assignments)
                if "$" in resolved or current_dir is None:
                    current_dir = None  # unresolved reference — unknown
                elif os.path.isabs(resolved):
                    current_dir = resolved
                else:
                    current_dir = os.path.normpath(os.path.join(current_dir or ".", resolved))
            i += 2
            continue
        if tok == "git":
            cwd_at[i] = current_dir
        i += 1
    return cwd_at


def resolve_toplevel(target_dir: str) -> str:
    """`git -C <dir> rev-parse --show-toplevel` with a short timeout;
    falls back to the raw dir on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", target_dir, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        toplevel = result.stdout.strip()
        if result.returncode == 0 and toplevel:
            return toplevel
    except Exception:
        pass
    return target_dir


def repo_has_unstaged_modifications(target_dir: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", target_dir, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in result.stdout.splitlines():
            if line.startswith(" M"):
                return True
    except Exception:
        pass
    return False


def main() -> int:
    payload = read_stdin_json()
    if not payload:
        return 0

    if tool_name(payload) != "Bash":
        return 0

    cmd = tool_input_field(payload, "command")
    if not cmd:
        return 0

    tokens = tokenize(cmd)

    # Deliberate override: a literal ALLOW_MAIN_CHECKOUT_GIT=1
    # env-assignment token anywhere in the command bypasses the guard.
    if "ALLOW_MAIN_CHECKOUT_GIT=1" in tokens:
        return allow("ALLOW_MAIN_CHECKOUT_GIT=1 escape hatch present")
    if os.environ.get("ALLOW_MAIN_CHECKOUT_GIT") == "1":
        return allow("ALLOW_MAIN_CHECKOUT_GIT=1 in process env")

    git_indices = find_git_invocation_indices(tokens)
    if not git_indices:
        return 0

    session_cwd = field(payload, "cwd", "cwd")
    agent_id = field(payload, "agent_id", "agentId")
    cwd_at_git = track_cwd_per_git_index(tokens, session_cwd)

    for gi in git_indices:
        repo_dir, subcmd = extract_repo_dir_and_subcommand(tokens, gi)
        if not subcmd:
            continue
        if not invocation_is_mutating(tokens, gi, subcmd):
            continue

        tracked_cwd = cwd_at_git.get(gi)
        target_dir = repo_dir or tracked_cwd or session_cwd or "."
        resolved = resolve_toplevel(target_dir)

        if path_is_worktree_or_scratch(resolved) or path_is_worktree_or_scratch(target_dir):
            continue

        if agent_id:
            return deny(
                f"This is a shared main checkout ('{resolved}') with a "
                f"subagent-initiated 'git {subcmd}' — {WORKTREE_HINT}."
            )

        if repo_has_unstaged_modifications(resolved):
            return deny(
                f"This is a shared main checkout ('{resolved}') with "
                f"uncommitted WIP (unstaged tracked modifications) and a "
                f"'git {subcmd}' would risk it being reverted — "
                f"{WORKTREE_HINT}."
            )

    return allow("no mutating git op targets an unsafe shared main checkout")


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, main)
