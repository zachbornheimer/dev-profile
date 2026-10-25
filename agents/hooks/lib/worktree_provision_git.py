"""The git verbs worktree-provision.py needs, on top of hook_common's Git seam.

A test substitutes a stub facade (or a fake ``Git``) without a real repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hook_common import GIT, Git

WORKTREE_LINE_PREFIX = "worktree "


@dataclass(frozen=True, slots=True)
class GitFacade:
    """Worktree and branch operations against one repository at a time."""

    git: Git = field(default=GIT)

    def show_toplevel(self, cwd: str) -> str | None:
        return self.git.run(cwd, "rev-parse", "--show-toplevel").text or None

    def is_inside_work_tree(self, repo_root: str) -> bool:
        return self.git.run(repo_root, "rev-parse", "--is-inside-work-tree").ok

    def branch_exists(self, repo_root: str, branch: str) -> bool:
        return self.git.run(repo_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}").ok

    def worktree_holding_branch(self, repo_root: str, branch: str) -> str | None:
        result = self.git.run(repo_root, "worktree", "list", "--porcelain")
        if not result.ok:
            return None
        want = f"branch refs/heads/{branch}"
        path = None
        for line in result.stdout.splitlines():
            if line.startswith(WORKTREE_LINE_PREFIX):
                path = line[len(WORKTREE_LINE_PREFIX) :]
            elif line == want:
                return path
        return None

    def relocate_worktree(self, repo_root: str, source: str, dest: str) -> bool:
        return self.git.run(repo_root, "worktree", "move", source, dest).ok

    def attach_worktree_to_branch(self, repo_root: str, dest: str, branch: str) -> bool:
        return self.git.run(repo_root, "worktree", "add", dest, branch).ok

    def current_branch(self, worktree: str) -> str:
        return self.git.run(worktree, "branch", "--show-current").text

    def remove_worktree(self, repo_root: str, path: str) -> bool:
        return self.git.run(repo_root, "worktree", "remove", path).ok

    def branch_is_empty(self, repo_root: str, branch: str) -> bool:
        """True when <branch> holds no commit another branch, remote, or tag lacks."""
        ahead = self.git.run(
            repo_root,
            "rev-list",
            "--count",
            f"refs/heads/{branch}",
            "--not",
            f"--exclude=refs/heads/{branch}",
            "--branches",
            "--remotes",
            "--tags",
        )
        return ahead.text == "0"

    def delete_branch(self, repo_root: str, branch: str) -> bool:
        return self.git.run(repo_root, "branch", "-D", branch).ok
