"""Recognizes a managed fork by its git shape, never by a repository name.

A checkout is managed when its `origin` owner is zachbornheimer and it has
either an `upstream` remote or a recorded GitHub parent. The mirror is that
parent's default branch. The answer is cached beside the clone and in this
process, so a later call in the same session does not repeat the lookup.

This module imports nothing from the hook runtime, so it moves with the hook
when the agents tree leaves its current checkout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

FORK_OWNER = "zachbornheimer"
DETECTION_TTL_SECONDS = 600
GIT_TIMEOUT_SECONDS = 2
GITHUB_REPO = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
_PROCESS_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def fork_flow(repo_name: str) -> str:
    """The one command that changes a managed fork, named for this clone."""
    name = repo_name or "<repo>"
    cli = "bun ~/.omp/agent/tools/fork/cli.ts"
    return (
        f"Start with `{cli} change {name} <branch>`, then "
        f"`{cli} land {name} <branch>` to ship. "
        f"`{cli} sync {name}` fast-forwards the mirror to upstream. "
        "never use branch protection."
    )


def _git(repo: str, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _github_repo(url: str) -> tuple[str, str] | None:
    match = GITHUB_REPO.fullmatch(url.strip())
    if not match:
        return None
    return match.group("owner"), match.group("repo")


def _common_dir(repo: str) -> str:
    common_dir = _git(repo, "rev-parse", "--git-common-dir")
    if not common_dir:
        return ""
    if not os.path.isabs(common_dir):
        common_dir = os.path.join(repo, common_dir)
    return os.path.normpath(common_dir)


def _cache_path(common_dir: str) -> str:
    override = os.environ.get("FORK_GUARD_CACHE_DIR")
    directory = override or os.path.join(common_dir, "fork-guard")
    return os.path.join(directory, "managed.json")


def _read_cache(common_dir: str) -> dict[str, str] | None:
    cached = _PROCESS_CACHE.get(common_dir)
    if cached is not None and time.monotonic() - cached[0] <= DETECTION_TTL_SECONDS:
        return cached[1]
    path = _cache_path(common_dir)
    try:
        age = time.time() - os.stat(path).st_mtime
        if age < 0 or age > DETECTION_TTL_SECONDS:
            return None
        loaded = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict):
        return None
    values = {str(key): str(value) for key, value in loaded.items()}
    if {"name", "mirror"} > values.keys():
        return None
    _PROCESS_CACHE[common_dir] = (time.monotonic(), values)
    return values


def _write_cache(common_dir: str, facts: dict[str, str]) -> None:
    path = _cache_path(common_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = f"{path}.{os.getpid()}.tmp"
        Path(temporary).write_text(json.dumps(facts))
        os.replace(temporary, path)
        _PROCESS_CACHE[common_dir] = (time.monotonic(), dict(facts))
    except OSError:
        return


def _remember(repo_key: str, common_dir: str, facts: dict[str, str]) -> None:
    _PROCESS_CACHE[repo_key] = (time.monotonic(), dict(facts))
    _write_cache(common_dir, facts)


def _upstream_default(url: str) -> str:
    """The parent repo's default branch, from a local record or one GitHub read."""
    parsed = _github_repo(url)
    if not parsed:
        return ""
    owner, name = parsed
    override = os.environ.get(f"FORK_GUARD_PARENT_DEFAULT_{owner}_{name}")
    if override:
        return override
    try:
        done = subprocess.run(
            ["gh", "api", f"repos/{owner}/{name}", "--jq", ".default_branch"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    branch = done.stdout.strip() if done.returncode == 0 else ""
    return branch if branch and " " not in branch and "/" not in branch else ""


def _recorded_parent(common_dir: str) -> str:
    """A parent recorded beside the clone, so a hook never has to ask GitHub."""
    for name in ("fork-parent", "config"):
        path = os.path.join(common_dir, name)
        try:
            text = Path(path).read_text()
        except OSError:
            continue
        if name == "fork-parent":
            return text.strip()
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "fork.parent":
                return value.strip()
    return ""


def _local_mirror(repo: str) -> str:
    """The mirror branch recorded in the clone, with no network call."""
    configured = _git(repo, "config", "--get", "fork.mirror")
    if configured and "/" not in configured and " " not in configured:
        return configured
    head = _git(repo, "symbolic-ref", "--short", "-q", "refs/remotes/upstream/HEAD")
    return head.removeprefix("upstream/") if head.startswith("upstream/") else ""


def managed_fork(repo: str) -> dict[str, str] | None:
    """The clone's fork facts, or None when it is not a zachbornheimer fork."""
    key = os.path.realpath(repo)
    remembered = _PROCESS_CACHE.get(key)
    if remembered is not None and time.monotonic() - remembered[0] <= DETECTION_TTL_SECONDS:
        return remembered[1] if remembered[1]["mirror"] else None
    common_dir = _common_dir(repo)
    if not common_dir:
        return None
    cached = _read_cache(common_dir)
    if cached is not None:
        _PROCESS_CACHE[key] = (time.monotonic(), cached)
        return cached if cached["mirror"] else None

    origin = _github_repo(_git(repo, "remote", "get-url", "origin"))
    if origin is None or origin[0] != FORK_OWNER:
        _remember(key, common_dir, {"name": "", "mirror": ""})
        return None
    upstream_url = _git(repo, "remote", "get-url", "upstream")
    parent = upstream_url or _recorded_parent(common_dir)
    if not parent:
        _remember(key, common_dir, {"name": "", "mirror": ""})
        return None
    mirror = _local_mirror(repo) or _upstream_default(parent)
    if not mirror and upstream_url:
        mirror = "main"
    if not mirror:
        return None
    facts = {"name": origin[1], "mirror": mirror}
    _remember(key, common_dir, facts)
    return facts
