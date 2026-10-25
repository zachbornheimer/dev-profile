"""The git verbs worktree-cleanup.py needs against a worktree about to be
removed, plus the main checkout that owns it — on top of hook_common's Git seam."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from hook_common import GIT, Git


@dataclass(frozen=True, slots=True)
class CleanupGitFacade:
    git: Git = field(default=GIT)

    def current_branch(self, worktree_path: str) -> str:
        return self.git.run(worktree_path, "branch", "--show-current").text

    def common_dir(self, worktree_path: str) -> str:
        return self.git.run(
            worktree_path, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).text

    def remove_worktree(self, main_root: str, worktree_path: str) -> bool:
        return self.git.run(main_root, "worktree", "remove", "--force", worktree_path).ok

    def remove_directory(self, worktree_path: str) -> None:
        shutil.rmtree(worktree_path, ignore_errors=True)

    def delete_branch(self, main_root: str, branch: str) -> bool:
        return self.git.run(main_root, "branch", "-D", branch).ok
