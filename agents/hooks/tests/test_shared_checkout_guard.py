"""shared-checkout-guard.py: stash list and stash show do not mutate a checkout."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOK_PATH = HOOKS_DIR / "shared-checkout-guard.py"

sys.path.insert(0, str(HOOKS_DIR / "lib"))
_spec = importlib.util.spec_from_file_location("shared_checkout_guard", HOOK_PATH)
guard = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(guard)

ORIGINAL_STASH_LIST = (
    "cd /Users/zbornheimer/Developer/Personal/zq; git status --porcelain | "
    "grep -v '^ M' ; git stash list | head -3; git diff --stat -- .evor/prompts/next.md | tail -1"
)


def git_indexes(command: str) -> list[int]:
    tokens = guard.tokenize(command)
    return [index for index, token in enumerate(tokens) if token == "git"]


@pytest.mark.parametrize(
    "command",
    [
        "git stash list",
        "git stash show -p stash@{0}",
        "git -C /repo stash list",
        ORIGINAL_STASH_LIST,
    ],
)
def test_stash_list_is_read_only(command: str) -> None:
    tokens = guard.tokenize(command)
    stash_indexes = [
        index
        for index in git_indexes(command)
        if guard.extract_repo_dir_and_subcommand(tokens, index)[1] == "stash"
    ]
    assert stash_indexes
    assert all(not guard.stash_is_mutating(tokens, index) for index in stash_indexes)


def test_stash_push_is_mutating() -> None:
    tokens = guard.tokenize("git stash push -u")
    assert guard.stash_is_mutating(tokens, 0)
