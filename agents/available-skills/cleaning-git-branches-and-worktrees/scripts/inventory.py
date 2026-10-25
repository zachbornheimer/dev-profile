#!/usr/bin/env python3
"""Read-only inventory of a repo's local branches and worktrees.

Sorts every local branch into exactly one class, strongest evidence first:

  protected   the default branch
  landed      its content is already in the base branch (ancestor, patch-id
              equivalent, or a merge-tree that changes nothing)
  merged-pr   a merged PR's head is this branch's tip (or contains it)
  open-pr     an open PR is based on this branch
  duplicate   same tip as another unlanded branch (keeps the best-named one)
  orphan      none of the above: unresolved work that needs evidence review

Worktree state is reported explicitly as clean, dirty, missing, or unknown.
Unknown is never equivalent to clean.

Never writes refs, the index, or working-tree files. `git merge-tree --write-tree`
may create unreachable Git objects while computing equivalence.

Usage: inventory.py [REPO] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PR_LIST_LIMIT = 5000
WORKERS = 16


@dataclass(slots=True)
class Git:
    root: Path

    def run(
        self, *args: str, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.root,
            text=True,
            capture_output=True,
            check=check,
            encoding="utf-8",
            errors="replace",
        )

    def out(
        self, *args: str, cwd: Path | None = None, check: bool = True
    ) -> str:
        return self.run(*args, cwd=cwd, check=check).stdout.strip()

    def ok(self, *args: str, cwd: Path | None = None) -> bool:
        return self.run(*args, cwd=cwd, check=False).returncode == 0


@dataclass(slots=True)
class Worktree:
    path: str
    head: str
    branch: str | None
    missing: bool
    dirty_files: int | None = None
    state: str = "unknown"  # clean|dirty|missing|unknown
    status_error: str = ""


@dataclass(slots=True)
class Branch:
    name: str
    sha: str
    upstream: str
    track: str
    date: str
    cls: str = ""
    evidence: str = ""
    ahead: int = 0
    pushed: bool = False
    pr: str = ""
    worktree: str = ""
    worktree_state: str = "none"
    dirty_files: int | None = None
    duplicates: list[str] = field(default_factory=list)


def repo_root(repo: str) -> Path:
    """Resolve and validate the repository root."""
    result = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    return Path(result.stdout.strip())


def default_base(git: Git) -> tuple[str, str]:
    """Resolve the remote default branch without silently assuming origin/main."""
    symbolic = git.run(
        "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False
    ).stdout.strip()
    if symbolic and git.ok("rev-parse", "--verify", symbolic):
        return symbolic, symbolic.split("/", 1)[1]

    for candidate in ("origin/main", "origin/master"):
        if git.ok("rev-parse", "--verify", candidate):
            return candidate, candidate.split("/", 1)[1]

    raise RuntimeError(
        "cannot resolve the remote default branch; fetch origin or configure origin/HEAD"
    )


def load_prs(root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load PR metadata and preserve whether lookup itself succeeded."""
    cli = shutil.which("ghx") or shutil.which("gh")
    if not cli:
        return [], {
            "status": "unavailable",
            "cli": "",
            "detail": "gh/ghx not found",
        }

    result = subprocess.run(
        [
            cli,
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            str(PR_LIST_LIMIT),
            "--json",
            "number,state,headRefName,headRefOid,url",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        return [], {"status": "unavailable", "cli": cli, "detail": detail}

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], {
            "status": "unavailable",
            "cli": cli,
            "detail": f"invalid PR JSON: {exc}",
        }

    if not isinstance(prs, list):
        return [], {
            "status": "unavailable",
            "cli": cli,
            "detail": "PR command returned a non-list JSON value",
        }

    return prs, {"status": "ok", "cli": cli, "detail": ""}


def load_worktrees(git: Git) -> list[Worktree]:
    """Load worktree metadata from Git's porcelain format."""
    trees: list[Worktree] = []
    current: dict[str, str] = {}

    for line in git.out("worktree", "list", "--porcelain").splitlines() + [""]:
        if line:
            key, _, value = line.partition(" ")
            current[key] = value
            continue

        if current:
            branch = current.get("branch", "").removeprefix("refs/heads/") or None
            path = current["worktree"]
            missing = not Path(path).exists()
            trees.append(
                Worktree(
                    path=path,
                    head=current.get("HEAD", ""),
                    branch=branch,
                    missing=missing,
                    state="missing" if missing else "unknown",
                )
            )
        current = {}

    return trees


def count_dirty(git: Git, tree: Worktree) -> None:
    """Record worktree cleanliness without collapsing errors into clean state."""
    if tree.missing:
        tree.state = "missing"
        tree.dirty_files = None
        return

    result = git.run("status", "--porcelain", cwd=Path(tree.path), check=False)
    if result.returncode != 0:
        tree.state = "unknown"
        tree.dirty_files = None
        tree.status_error = result.stderr.strip() or f"exit {result.returncode}"
        return

    tree.dirty_files = len(result.stdout.splitlines())
    tree.state = "dirty" if tree.dirty_files else "clean"


def load_branches(git: Git) -> list[Branch]:
    """Load local branch metadata in one Git query."""
    fmt = (
        "%(refname:short)%09%(objectname)%09%(upstream:short)%09"
        "%(upstream:track)%09%(committerdate:short)"
    )
    rows = git.out("for-each-ref", "refs/heads", f"--format={fmt}").splitlines()
    return [Branch(*row.split("\t")) for row in rows]


def content_landed(git: Git, base: str, sha: str) -> str:
    """Return deterministic evidence when a branch's content is already in base."""
    if git.ok("merge-base", "--is-ancestor", sha, base):
        return "ancestor of base"

    cherry = git.run("cherry", base, sha, check=False)
    if cherry.returncode == 0:
        lines = cherry.stdout.strip().splitlines()
        if lines and all(line.startswith("-") for line in lines):
            return "every commit patch-equivalent in base"

    merged = git.run("merge-tree", "--write-tree", base, sha, check=False)
    tokens = merged.stdout.split()
    if merged.returncode == 0 and tokens:
        base_tree = git.out("rev-parse", f"{base}^{{tree}}")
        if tokens[0] == base_tree:
            return "merging into base changes nothing (squash-landed)"

    return ""


def pr_match(
    git: Git, branch: Branch, prs_by_head: dict[str, list[dict[str, Any]]]
) -> tuple[str, str] | None:
    """Return the strongest PR relationship known for a branch."""
    for pr in prs_by_head.get(branch.name, []):
        if pr.get("state") == "OPEN":
            return "open-pr", str(pr.get("url", ""))

    for pr in prs_by_head.get(branch.name, []):
        oid = str(pr.get("headRefOid", ""))
        if pr.get("state") != "MERGED" or not oid:
            continue
        if oid == branch.sha:
            return "merged-pr", str(pr.get("url", ""))
        if git.ok("cat-file", "-e", f"{oid}^{{commit}}") and git.ok(
            "merge-base", "--is-ancestor", branch.sha, oid
        ):
            return "merged-pr", str(pr.get("url", ""))

    return None


def classify(
    git: Git,
    base: str,
    default: str,
    branch: Branch,
    prs_by_head: dict[str, list[dict[str, Any]]],
) -> None:
    """Classify one local branch using strongest deterministic evidence first."""
    if branch.name == default:
        branch.cls, branch.evidence = "protected", "default branch"
        return

    # Open PRs remain protected even when equivalent content already exists.
    match = pr_match(git, branch, prs_by_head)
    if match and match[0] == "open-pr":
        branch.cls, branch.pr = match
        branch.evidence = f"PR {match[1]}"
        return

    if evidence := content_landed(git, base, branch.sha):
        branch.cls, branch.evidence = "landed", evidence
        return

    if match:
        branch.cls, branch.pr = match
        branch.evidence = f"PR {match[1]}"
        return

    branch.cls = "orphan"
    ahead = git.run("rev-list", "--count", f"{base}..{branch.sha}", check=False)
    branch.ahead = int(ahead.stdout.strip()) if ahead.returncode == 0 else 0
    branch.pushed = (
        bool(branch.upstream)
        and "gone" not in branch.track
        and git.ok("merge-base", "--is-ancestor", branch.sha, branch.upstream)
    )


def mark_duplicates(branches: list[Branch]) -> None:
    """Mark removable orphan refs that share a tip with a canonical copy."""
    by_sha: dict[str, list[Branch]] = defaultdict(list)
    for branch in branches:
        if branch.cls in {"orphan", "open-pr"}:
            by_sha[branch.sha].append(branch)

    for group in by_sha.values():
        if len(group) < 2:
            continue

        # Prefer open PRs, then checked-out worktrees, then the shortest name.
        group.sort(
            key=lambda branch: (
                branch.cls != "open-pr",
                not branch.worktree,
                len(branch.name),
                branch.name,
            )
        )
        keeper = group[0]
        keeper.duplicates = [branch.name for branch in group[1:]]

        for duplicate in group[1:]:
            if duplicate.cls == "orphan" and not duplicate.worktree:
                duplicate.cls = "duplicate"
                duplicate.evidence = f"same tip as {keeper.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--out", default="-")
    args = parser.parse_args()

    git = Git(repo_root(args.repo))
    base, default = default_base(git)
    prs, pr_lookup = load_prs(git.root)

    prs_by_head: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pr in prs:
        head = str(pr.get("headRefName", ""))
        if head:
            prs_by_head[head].append(pr)

    trees = load_worktrees(git)
    branches = load_branches(git)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda tree: count_dirty(git, tree), trees))
        list(
            pool.map(
                lambda branch: classify(git, base, default, branch, prs_by_head),
                branches,
            )
        )

    tree_by_branch = {tree.branch: tree for tree in trees if tree.branch}
    for branch in branches:
        tree = tree_by_branch.get(branch.name)
        if tree:
            branch.worktree = tree.path
            branch.worktree_state = tree.state
            branch.dirty_files = tree.dirty_files

    mark_duplicates(branches)

    report = {
        "repo": str(git.root),
        "base": base,
        "base_sha": git.out("rev-parse", base),
        "pr_lookup": pr_lookup,
        "summary": {
            "branches": dict(Counter(branch.cls for branch in branches)),
            "orphans_pushed": sum(
                branch.cls == "orphan" and branch.pushed for branch in branches
            ),
            "worktrees": len(trees),
            "worktrees_clean": sum(tree.state == "clean" for tree in trees),
            "worktrees_dirty": sum(tree.state == "dirty" for tree in trees),
            "worktrees_missing": sum(tree.state == "missing" for tree in trees),
            "worktrees_unknown": sum(tree.state == "unknown" for tree in trees),
            "worktrees_detached": sum(tree.branch is None for tree in trees),
        },
        "branches": [
            asdict(branch)
            for branch in sorted(branches, key=lambda branch: (branch.cls, branch.name))
        ],
        "worktrees": [asdict(tree) for tree in trees],
    }

    text = json.dumps(report, indent=2)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(json.dumps(report["summary"], indent=2))

    if pr_lookup["status"] != "ok":
        print(
            f"warning: PR lookup unavailable: {pr_lookup['detail']}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
