"""Pytest wiring for hook tests: ``hooks`` runs a hook by path in an isolated state dir."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from hook_harness import HookRunner

# The global git config runs hk on every commit unless HK=0. Tests commit in throwaway
# repos, so switch hk off for the whole suite; subprocess git calls inherit this.
os.environ.setdefault("HK", "0")

HOOKS_DIR = Path(__file__).resolve().parents[1]
CHEZMOI_EXECUTABLE_PREFIX = "executable_"


def hook_path(name: str) -> Path:
    """Locate hook ``name`` in the live tree (bare) or the chezmoi source tree (``executable_``)."""
    candidates = (HOOKS_DIR / name, HOOKS_DIR / f"{CHEZMOI_EXECUTABLE_PREFIX}{name}")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"hook {name!r} not found at either {candidates[0]} or {candidates[1]}")


@pytest.fixture
def hooks(tmp_path: Path) -> HookRunner:
    return HookRunner(state_root=tmp_path)
