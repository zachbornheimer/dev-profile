#!/usr/bin/env python3
"""Refuse rm/trash/unlink/mv of tip-verify.lock + tip-verify.marker while tip-VERIFY parked.

ZYS-1230 wipe #8 — Claude 924a99da hand-trashed tip-verify.lock outside install-guard.

CLI:
  tip-verify-rm-deny.py --check 'trash ~/.local/state/agentmux/tip-verify.lock'
  tip-verify-rm-deny.py --hook-stdin   # Claude PreToolUse JSON → deny JSON on stdout

Exit (--check): 0 allow, 1 deny (message on stderr).

Nuclear: AGENTMUX_INSTALL_CLEAR_TIP_VERIFY_I_OWN_THIS=1 or AGENTMUX_TIP_VERIFY_ALLOW_RM=1
(as process env or command-prefix assignment).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DENY_MSG = (
    "tip-VERIFY protect (ZYS-1230 wipe #8): refuse deleting/moving tip-verify.lock or "
    "tip-verify.marker while tip is parked. Do not trash/rm those files to bypass "
    "install-guard. Tip owner: AGENTMUX_INSTALL_CLEAR_TIP_VERIFY=1 when HEAD matches "
    "lock/marker sha, or AGENTMUX_INSTALL_CLEAR_TIP_VERIFY_I_OWN_THIS=1 (audited nuclear). "
    "See scripts/tip-verify-rm-deny.sh / install-guard.sh."
)
NUCLEAR = (
    "AGENTMUX_INSTALL_CLEAR_TIP_VERIFY_I_OWN_THIS",
    "AGENTMUX_TIP_VERIFY_ALLOW_RM",
)
DESTRUCTIVE = frozenset({"rm", "trash", "unlink", "srm", "gomi"})
PROTECTED_BASENAMES = frozenset({"tip-verify.lock", "tip-verify.marker"})


def state_dir() -> Path:
    return Path(
        os.environ.get("AGENTMUX_TIP_VERIFY_STATE_DIR")
        or (Path.home() / ".local/state/agentmux")
    )


def tip_parked(d: Path) -> bool:
    return (d / "tip-verify.lock").is_file() or (d / "tip-verify.marker").is_file()


def nuclear_set(cmd: str) -> bool:
    for name in NUCLEAR:
        val = os.environ.get(name)
        if val and val != "0":
            return True
        if re.search(rf"(^|[\s;&|]){re.escape(name)}=0([\s;&]|$)", cmd):
            continue
        if re.search(rf"(^|[\s;&|]){re.escape(name)}=([^\s;&|]*)", cmd):
            return True
    return False


def expand_word(w: str, d: Path) -> str:
    home = str(Path.home())
    if w == "~":
        return home
    if w.startswith("~/"):
        w = home + w[1:]
    w = w.replace("$HOME", home).replace("${HOME}", home)
    w = w.replace("$AGENTMUX_TIP_VERIFY_STATE_DIR", str(d)).replace(
        "${AGENTMUX_TIP_VERIFY_STATE_DIR}", str(d)
    )
    return w


def is_protected_word(w: str, d: Path) -> bool:
    exp = expand_word(w, d)
    base = Path(exp).name
    if (
        base in PROTECTED_BASENAMES
        or base == "tip-verify.*"
        or "*" in base
        and base.startswith("tip-verify.")
    ):
        return True
    if exp.endswith(("/tip-verify.lock", "/tip-verify.marker")):
        return True
    if exp.endswith("/tip-verify.*"):
        return True
    for name in PROTECTED_BASENAMES:
        target = d / name
        if exp == str(target) or exp == f"~/.local/state/agentmux/{name}":
            return True
        try:
            if Path(exp).resolve() == target.resolve():
                return True
        except OSError:
            pass
    return False


def mentions_protected(cmd: str, d: Path) -> bool:
    home = str(Path.home())
    variants = [
        str(d / "tip-verify.lock"),
        str(d / "tip-verify.marker"),
        f"{home}/.local/state/agentmux/tip-verify.lock",
        f"{home}/.local/state/agentmux/tip-verify.marker",
        "~/.local/state/agentmux/tip-verify.lock",
        "~/.local/state/agentmux/tip-verify.marker",
        "tip-verify.lock",
        "tip-verify.marker",
        "tip-verify.*",
    ]
    return any(v in cmd for v in variants)


def split_chunks(cmd: str) -> list[str]:
    return re.split(r"&&|\|\||;|\|", cmd)


def strip_leading(words: list[str]) -> list[str]:
    i = 0
    while i < len(words):
        w = words[i]
        if "=" in w and not w.startswith("-") and "/" not in w.split("=", 1)[0]:
            i += 1
            continue
        if w in {"sudo", "command", "env", "nice", "nohup"}:
            i += 1
            continue
        break
    return words[i:]


def should_deny(cmd: str) -> bool:
    d = state_dir()
    if nuclear_set(cmd) or not tip_parked(d):
        return False
    if not mentions_protected(cmd, d):
        return False
    if (
        re.search(r"(^|[\s;&|])find\b", cmd)
        and mentions_protected(cmd, d)
        and re.search(r"-delete|(^|[\s;&|])rm\b|\bunlink\b|\btrash\b", cmd)
    ):
        return True
    for chunk in split_chunks(cmd):
        chunk = chunk.strip()
        if not chunk:
            continue
        words = strip_leading(chunk.split())
        if not words:
            continue
        verb = Path(words[0]).name
        idx = 0
        if verb == "gio" and len(words) > 1 and words[1] == "trash":
            verb = "trash"
            idx = 1
        args = words[idx + 1 :]
        if verb == "mv":
            for a in args:
                if a.startswith("-"):
                    continue
                if is_protected_word(a, d):
                    return True
            continue
        if verb in DESTRUCTIVE:
            for a in args:
                if a.startswith("-"):
                    continue
                if is_protected_word(a, d):
                    return True
                exp = expand_word(a, d).rstrip("/")
                if exp == str(d):
                    return True
    return False


def deny_payload(reason: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        indent=2,
        ensure_ascii=False,
    )


def usage() -> None:
    prog = Path(sys.argv[0]).name
    print(f"usage: {prog} --check <command-string>", file=sys.stderr)
    print(f"       {prog} --hook-stdin", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str]) -> int:
    if not argv:
        usage()
    if argv[0] in {"-h", "--help"}:
        usage()
    if argv[0] == "--check":
        if len(argv) < 2:
            usage()
        cmd = " ".join(argv[1:])
        if should_deny(cmd):
            print(DENY_MSG, file=sys.stderr)
            return 1
        return 0
    if argv[0] == "--hook-stdin":
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return 0
        ti = data.get("tool_input") or data.get("toolInput") or {}
        cmd = ti.get("command") or ""
        if not cmd:
            return 0
        if should_deny(cmd):
            print(deny_payload(DENY_MSG))
        return 0
    usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
