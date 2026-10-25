"""Facade over the local filesystem/git state needed to prefer a `~/Developer`
clone of a repo over a legacy `~/Dropbox/...` clone in the taxonomy's leaf
`local_path`.

This is the builder's one filesystem-beyond-its-input-files boundary: every
other rule in taxonomy_rules.py is a pure function. Keeping the git/os calls
behind this module means taxonomy_rules.py and its tests never touch a real
disk or subprocess.
"""

from __future__ import annotations

import os
import re
import subprocess

_ORIGIN_RE = re.compile(r"(?:github\.com[:/])([^/]+/[^/]+?)(?:\.git)?$")

# Software-Automation-Holdings-LLC is a known accidental duplicate checkout
# folder (see machine-layout notes); its clones lose to the canonical org
# folder when both exist for the same origin.
_LEGACY_ORG_FOLDERS = frozenset({"Software-Automation-Holdings-LLC"})


def _normalize_origin(url: str) -> str | None:
    match = _ORIGIN_RE.search(url.strip())
    return match.group(1) if match else None


def _read_origin(repo_path: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def _candidate_score(
    repo_path: str, is_worktree: bool, org_folder: str, repo_name: str
) -> tuple[bool, bool, bool, str]:
    basename_mismatch = os.path.basename(repo_path).lower() != repo_name.lower()
    return (is_worktree, org_folder in _LEGACY_ORG_FOLDERS, basename_mismatch, repo_path)


def discover_developer_clones(developer_root: str) -> dict[str, str]:
    """Scan `developer_root` (typically `~/Developer`) one and two levels deep
    for git checkouts, and return the best local clone path per `org/repo`
    origin. "Best" prefers a real checkout over a linked worktree, the
    canonical org folder over a known-legacy duplicate, and a directory whose
    basename matches the repo name."""
    candidates: dict[str, list[tuple[str, bool, str]]] = {}
    if not os.path.isdir(developer_root):
        return {}

    for org_folder in sorted(os.listdir(developer_root)):
        org_path = os.path.join(developer_root, org_folder)
        if not os.path.isdir(org_path) or os.path.islink(org_path):
            continue
        # A repo directly under developer_root (org_path is itself a repo)
        # and one level of org/repo nesting are both in scope.
        for repo_path, is_worktree in _git_checkouts_in(org_path):
            origin = _normalize_origin(_read_origin(repo_path))
            if origin:
                candidates.setdefault(origin, []).append((repo_path, is_worktree, org_folder))
        if os.path.exists(os.path.join(org_path, ".git")):
            is_worktree = os.path.isfile(os.path.join(org_path, ".git"))
            origin = _normalize_origin(_read_origin(org_path))
            if origin:
                candidates.setdefault(origin, []).append(
                    (org_path, is_worktree, os.path.basename(developer_root))
                )

    resolved: dict[str, str] = {}
    for origin, entries in candidates.items():
        repo_name = origin.split("/", 1)[1]
        best = min(
            entries,
            key=lambda entry: _candidate_score(entry[0], entry[1], entry[2], repo_name),
        )
        resolved[origin] = best[0]
    return resolved


def _git_checkouts_in(org_path: str) -> list[tuple[str, bool]]:
    found = []
    try:
        entries = sorted(os.listdir(org_path))
    except OSError:
        return found
    for name in entries:
        repo_path = os.path.join(org_path, name)
        git_path = os.path.join(repo_path, ".git")
        if not os.path.exists(git_path):
            continue
        found.append((repo_path, os.path.isfile(git_path)))
    return found
