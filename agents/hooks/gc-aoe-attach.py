#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SessionStart — make every Gas City session attachable from Agent of Empires.

Inside a Gas City session (GC_CITY + GC_SESSION_ID set) this ensures one AoE
terminal entry exists whose command is `gc session attach <alias>`, then
starts it. Any harness works: the AoE tool is picked from GC_PROVIDER
(gc-claude, gc-codex, gc-grok custom agents). It also sizes Gas City's tmux
windows to the largest client, so AoE's small attach client never shrinks
the window Zach is looking at.

Scope: GC_AOE_ATTACH=named (default: sessions with an alias), all, or off.
Outside Gas City it is a no-op. The `aoe` calls run in a detached child so
session start never waits on AoE; results go to <state>/gc-aoe-attach.log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from gc_aoe_attach_plan import (
    DEFAULT_SCOPE,
    SCOPE_ENV,
    Action,
    AoeEntry,
    AttachPlan,
    plan_attach,
    session_from_env,
)

APPLY_FLAG = "--apply"
AOE_BIN = os.environ.get("GC_AOE_ATTACH_AOE_BIN", "aoe")
AOE_TIMEOUT_SECS = 60
LOG_NAME = "gc-aoe-attach.log"
AOE_LIVE_STATE = "live"
GAS_CITY_TMUX_ENV = frozenset({"TMUX", "TMUX_PANE"})
STATE_DIR = Path(
    os.environ.get("HC_STATE_DIR_OVERRIDE", Path.home() / ".agents/hooks/state")
)


class AoeCli:
    """The `aoe` command line, the one boundary this hook writes through."""

    def entries(self) -> list[AoeEntry]:
        """Live entries only: a trashed entry keeps its title but can't be started."""
        listing = json.loads(self._run("list", "--json") or "[]")
        return [
            AoeEntry(e["id"], e["title"])
            for e in listing
            if e.get("state", AOE_LIVE_STATE) == AOE_LIVE_STATE
        ]

    def add(self, plan: AttachPlan) -> str:
        return self._run(
            "add",
            plan.city,
            "-t",
            plan.title,
            "--tool",
            plan.tool,
            "--extra-args",
            plan.extra_args,
            "-l",
        )

    def start(self, entry_id: str) -> str:
        return self._run("session", "start", entry_id)

    def _run(self, *args: str) -> str:
        # Without this, aoe sees Gas City's $TMUX and builds its panes on Gas City's
        # tmux server, where AoE can't find them and reports Error.
        env = {k: v for k, v in os.environ.items() if k not in GAS_CITY_TMUX_ENV}
        done = subprocess.run(
            [AOE_BIN, *args],
            capture_output=True,
            text=True,
            timeout=AOE_TIMEOUT_SECS,
            check=False,
            env=env,
        )
        return (done.stdout or done.stderr).strip()


def size_windows_to_largest_client() -> None:
    """Gas City sets a window-local `window-size latest`, so set this window as well as the default."""
    socket = os.environ.get("TMUX", "").split(",")[0]
    if not socket:
        return
    targets = [["-g"]]
    pane = os.environ.get("TMUX_PANE", "")
    if pane:
        targets.append(["-t", pane])
    for target in targets:
        subprocess.run(
            [
                "tmux",
                "-S",
                socket,
                "set-window-option",
                *target,
                "window-size",
                "largest",
            ],
            capture_output=True,
            timeout=AOE_TIMEOUT_SECS,
            check=False,
        )


def log(line: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with (STATE_DIR / LOG_NAME).open("a") as f:
        f.write(f"{stamp}\t{line}\n")


def apply(aoe: AoeCli) -> None:
    session = session_from_env(os.environ)
    if session is None:
        return
    size_windows_to_largest_client()
    plan = plan_attach(session, os.environ.get(SCOPE_ENV, DEFAULT_SCOPE), aoe.entries())
    if plan is None:
        log(
            f"skip\t{session.title}\tout of scope or unknown provider {session.provider!r}"
        )
        return
    result = aoe.add(plan) if plan.action is Action.ADD else aoe.start(plan.entry_id)
    log(
        f"{plan.action.value}\t{plan.title}\t{result.splitlines()[-1] if result else ''}"
    )


def main() -> int:
    if APPLY_FLAG in sys.argv:
        apply(AoeCli())
        return 0
    if session_from_env(os.environ) is None:
        return 0
    sys.stdin.read()  # drain the hook payload; the environment carries everything needed
    subprocess.Popen(
        [sys.executable, __file__, APPLY_FLAG],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
