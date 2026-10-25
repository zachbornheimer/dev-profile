"""Path predicates for orchestrator-only.py: worktree containment, scratch/
memory/learn exemptions, and the tilde/$HOME normalization they all share.

Ported from the path-classifying functions in orchestrator-only.sh
(normalize_path, memory_path_allowed, learn_run_path_allowed, resolve_path,
path_is_scratch, path_is_tracked_in_git, path_is_worktree, path_is_inside).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hook_common import GIT, Git

HOME = str(Path.home())

# Matched as path components after resolution (trailing-slash boundary),
# never as a substring of a directory name.
WORKTREE_DIR_MARKER = "/.worktrees/"
CLAUDE_WORKTREE_DIR_MARKER = "/.claude/worktrees/"

LEARN_TRASH_PREFIX = f"{HOME}/.grok/learn/trash/"
LEARN_RUN_STAMP = re.compile(r"^20\d{6}-\d{6}$")
LEARN_LEAF_DIRS_MD_ONLY = frozenset({"reduce", "verify"})
LEARN_LEAF_DIR_PATCHES = "patches"
LEARN_PATCHES_SUFFIXES = (".md", ".json", ".jsonl")
LEARN_TOP_LEVEL_ALLOWED = re.compile(r"^(map.*\.md|report\.md|actions\.json|decisions\.jsonl)$")


def normalize_path(path: str) -> str:
    """``~/x`` and ``$HOME/x`` forms resolved to an absolute ``$HOME``-relative path."""
    if path == "~":
        return HOME
    if path.startswith("~/"):
        return f"{HOME}/{path[2:]}"
    if path == "$HOME":
        return HOME
    if path.startswith("$HOME/"):
        return f"{HOME}/{path[len('$HOME/') :]}"
    return path


def memory_path_allowed(path: str) -> bool:
    """True under this machine's ``~/.claude/projects/*/memory/`` tree."""
    resolved = normalize_path(path)
    prefix = f"{HOME}/.claude/projects/"
    if not resolved.startswith(prefix):
        return False
    rest = resolved[len(prefix) :]
    parts = rest.split("/")
    return len(parts) >= 3 and parts[1] == "memory"


def learn_run_path_allowed(path: str) -> bool:
    """True for a ``/learn/<YYYYMMDD-HHMMSS>/`` run artifact ``learn`` owns."""
    resolved = normalize_path(path)
    if resolved.startswith(LEARN_TRASH_PREFIX):
        return False

    components = resolved.lstrip("/").split("/")
    try:
        learn_index = components.index("learn")
    except ValueError:
        return False

    after_learn = components[learn_index + 1 :]
    if len(after_learn) < 2:
        return False

    run_stamp, *rel = after_learn
    if not LEARN_RUN_STAMP.match(run_stamp):
        return False

    if len(rel) == 1:
        return bool(LEARN_TOP_LEVEL_ALLOWED.match(rel[0]))
    if len(rel) == 2:
        directory, filename = rel
        if directory in LEARN_LEAF_DIRS_MD_ONLY:
            return filename.endswith(".md")
        if directory == LEARN_LEAF_DIR_PATCHES:
            return filename.endswith(LEARN_PATCHES_SUFFIXES)
    return False


def resolve_path(path: str, cwd: str) -> str:
    """Best-effort absolute-ify: no ``..`` collapsing, just enough to prefix-match."""
    if path.startswith("/"):
        return path
    if path == "~":
        return HOME
    if path.startswith("~/"):
        return f"{HOME}/{path[2:]}"
    return f"{cwd.rstrip('/')}/{path}"


def path_is_inside(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def path_is_scratch(resolved_path: str, scratchpad_dir: str = "", tmpdir: str = "") -> bool:
    """Under this session's scratchpad_dir, $TMPDIR, /tmp, or /var/folders.

    ``scratchpad_dir``/``tmpdir`` are passed in by the caller (read once from
    the event/environment at the entry point) rather than read here, so this
    predicate stays a pure function of its arguments.
    """
    if scratchpad_dir and resolved_path.startswith(scratchpad_dir.rstrip("/") + "/"):
        return True
    if tmpdir and resolved_path.startswith(tmpdir.rstrip("/") + "/"):
        return True
    return resolved_path.startswith(("/tmp/", "/var/folders/"))


@dataclass(frozen=True, slots=True)
class ScratchLocations:
    """The two env-derived roots every scratch check needs, read once at the
    entry point and threaded through instead of re-read per predicate."""

    scratchpad_dir: str = ""
    tmpdir: str = ""

    def contains(self, resolved_path: str) -> bool:
        return path_is_scratch(resolved_path, self.scratchpad_dir, self.tmpdir)


def path_is_tracked_in_git(resolved_path: str, probe: Git = GIT) -> bool:
    """True only if the path's directory is a git work tree AND git already tracks it."""
    directory = str(PurePosixPath(resolved_path).parent)
    basename = PurePosixPath(resolved_path).name
    exit_code, _ = probe.run(directory, "rev-parse", "--is-inside-work-tree")
    if exit_code != 0:
        return False
    exit_code, _ = probe.run(directory, "ls-files", "--error-unmatch", "--", basename)
    return exit_code == 0


def canonical_path(path: str) -> str:
    """realpath when it exists (follows symlinks); the input unchanged otherwise."""
    if not path:
        return ""
    try:
        return str(Path(path).resolve(strict=True))
    except OSError:
        return path


def path_is_worktree(path: str) -> bool:
    """True for a canonical ``.worktrees/...`` or ``.claude/worktrees/...`` path."""
    resolved = canonical_path(path)
    if not resolved:
        return False
    checked = resolved + "/"
    return WORKTREE_DIR_MARKER in checked or CLAUDE_WORKTREE_DIR_MARKER in checked
