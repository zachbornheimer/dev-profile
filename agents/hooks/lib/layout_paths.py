"""Path normalization and forbidden-location matching for layout-guard.

Port of layout-guard.sh's normalize_path / path_in_forbidden_location /
destination_is_non_developer_home_direct — pure functions over a single
already-extracted destination path, never over raw command text.
"""

from __future__ import annotations

import os
import re

CANONICAL_DESTINATION_HINT = (
    "Canonical destination: ~/Developer/<Org>/... for a repo, or "
    "<repo-parent>/.worktrees/<repo>-<slug>/ for a worktree (see machine-layout.md)."
)

_FORBIDDEN_HOME_DIRS = (
    "work",
    "projects",
    "src",
    "code",
    "repos",
    "repo",
    "workspace",
    "workspaces",
    "dev",
    "Development",
)
LLC_SEGMENT_RE = re.compile(r"(^|/)[^/]*-LLC(/|$)")


def home_dir() -> str:
    return os.environ.get("HOME", os.path.expanduser("~"))


def normalize_path(destination: str) -> str:
    """Rewrites ``~/...``, bare ``~``, ``$HOME/...``, or bare ``$HOME`` to an absolute path."""
    home = home_dir()
    if destination == "~":
        return home
    if destination.startswith("~/"):
        return f"{home}/{destination[2:]}"
    if destination == "$HOME":
        return home
    if destination.startswith("$HOME/"):
        return f"{home}/{destination[len('$HOME/') :]}"
    return destination


def _forbidden_home_dir_re(home: str) -> re.Pattern[str]:
    names = "|".join(_FORBIDDEN_HOME_DIRS)
    return re.compile(rf"{re.escape(home)}/({names})(/|$)")


def path_in_forbidden_location(path: str) -> bool:
    if not path:
        return False
    if _forbidden_home_dir_re(home_dir()).search(path):
        return True
    return bool(LLC_SEGMENT_RE.search(path))


def destination_is_non_developer_home_direct(destination: str) -> bool:
    """True for $HOME top-level, ~/Desktop*, ~/Dropbox*, or bare $HOME/<name> not under Developer."""
    home = home_dir()
    if destination in (home, f"{home}/"):
        return True
    if destination == f"{home}/Desktop" or destination.startswith(f"{home}/Desktop/"):
        return True
    if destination == f"{home}/Dropbox" or destination.startswith(f"{home}/Dropbox/"):
        return True
    if destination.startswith(f"{home}/Developer/"):
        return False
    return destination.startswith(f"{home}/")
