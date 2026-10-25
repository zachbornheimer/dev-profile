#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash) — deny rm/trash/unlink/mv of tip-verify.lock + tip-verify.marker
while tip-VERIFY is parked (ZYS-1230 wipe #8; Claude 924a99da).

SoT logic: agentmux scripts/tip-verify-rm-deny.py (also vendored at
lib/tip_verify_rm_deny.py for live protect before/without a repo checkout).
Nuclear override: AGENTMUX_INSTALL_CLEAR_TIP_VERIFY_I_OWN_THIS=1 (or
AGENTMUX_TIP_VERIFY_ALLOW_RM=1). After editing ~/.agents, run
`chezmoi re-add ~/.agents`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "tip-verify-rm-deny"


def _load_checker():
    """Prefer agentmux repo SoT; fall back to vendored lib copy."""
    candidates: list[Path] = []
    import os

    for key in ("AGENTMUX_REPO", "CLAUDE_PROJECT_DIR"):
        root = os.environ.get(key)
        if root:
            candidates.append(Path(root) / "scripts/tip-verify-rm-deny.py")
    # Known worktree / checkout locations (best-effort)
    home = Path.home()
    candidates.extend(
        [
            home
            / "Developer/Personal/.worktrees/agentmux-fix-zys-1230-tip-lock-rm-deny/scripts/tip-verify-rm-deny.py",
            home / "Developer/Personal/agentmux/scripts/tip-verify-rm-deny.py",
            Path(__file__).resolve().parent / "lib" / "tip_verify_rm_deny.py",
        ]
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("tip_verify_rm_deny_sot", path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "should_deny") and hasattr(mod, "DENY_MSG"):
            return mod
    return None


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name != "Bash":
        return None
    command = event.tool_input("command")
    if not command:
        return None
    mod = _load_checker()
    if mod is None:
        return Decision.no_objection("checker-missing")
    if mod.should_deny(command):
        return Decision.deny(mod.DENY_MSG)
    return Decision.no_objection("tip-verify-rm-ok")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
