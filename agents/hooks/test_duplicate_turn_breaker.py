#!/usr/bin/env python3
"""Exercise duplicate-turn-breaker.py against synthetic Stop events.

Default run (the atask proof): a turn whose final message repeats the previous
exchange's reply verbatim, with no tool runs, BLOCKS once and then never again
in the same session.

--allow-repeat (the atask regression): HC_DUPLICATE_BREAKER_OFF makes the same
event pass — the feature off is the pre-change behavior.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "duplicate-turn-breaker.py"

REPORT_A = (
    "I cannot install anything yet. Two things block it.\n\n"
    "- **I can't identify the tool.** It isn't in ~/.agents or ~/.claude, and no "
    "earlier session mentions it. I can't tell whether it's a repo, a package, or "
    "a typo. Send me the repo URL, package name, or install command.\n"
    "- **The shell tool is disabled in this session**, including for subagents. "
    "I can't run an installer, set an install-path variable, or check what it "
    "wrote until it's re-enabled. Once I have the source, I'll install it with "
    "the target forced to the roster directory, then check nothing else changed."
)

REPORT_B = (
    "The install finished. The helper program is runnable and passed a test with "
    "a fake home folder: a new skill moved into the roster, a duplicate stayed "
    "put with an error, and the lock file records the source repository. Nothing "
    "was written outside the roster directory during the trial."
)


def _compact(obj: object) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _user(text: str) -> str:
    return _compact({"type": "user", "message": {"content": text}, "timestamp": "2026-10-23T01:00:00Z"})


def _reply(text: str) -> str:
    return _compact({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


def _tool_pair(id: str) -> list[str]:
    return [
        _compact(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": id, "name": "Read", "input": {"file_path": "/x"}}]},
            }
        ),
        _compact(
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": id, "content": "ok"}]},
            }
        ),
    ]


def write_transcript(path: Path, *, final_reply: str, final_tools: bool = False) -> Path:
    """Two exchanges; the second answers with final_reply and optionally runs a tool."""
    lines = [
        _user("Please set up the skills tool globally"),
        _reply(REPORT_A),
        _user("ok"),
    ]
    if final_tools:
        lines += _tool_pair("t1")
    lines.append(_reply(final_reply))
    path.write_text("\n".join(lines) + "\n")
    return path


def run_hook(transcript: Path, message: str, state_dir: Path, session: str = "s1", off: bool = False) -> dict | None:
    payload = json.dumps(
        {"session_id": session, "transcript_path": str(transcript), "last_assistant_message": message}
    )
    env = dict(os.environ, HC_STATE_DIR_OVERRIDE=str(state_dir))
    if off:
        env["HC_DUPLICATE_BREAKER_OFF"] = "1"
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )
    if done.returncode != 0:
        raise AssertionError(f"hook exited {done.returncode}: {done.stderr[-400:]}")
    if not done.stdout.strip():
        return None
    return json.loads(done.stdout)


def main() -> int:
    allow_repeat = "--allow-repeat" in sys.argv
    failures: list[str] = []

    def check(name: str, got: dict | None, want_block: bool) -> None:
        blocked = bool(got and got.get("decision") == "block")
        if blocked != want_block:
            failures.append(f"{name}: blocked={blocked}, want {want_block}: {json.dumps(got)[:200]}")
        else:
            print(f"ok {name}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = root / "state"
        state.mkdir()

        (root / "d1").mkdir(parents=True)
        dup = write_transcript(root / "d1" / "transcript.jsonl", final_reply=REPORT_A)

        if allow_repeat:
            got = run_hook(dup, REPORT_A, state, off=True)
            check("allow-repeat: identical repeat passes with the breaker off", got, want_block=False)
            return finish(failures)

        check("identical repeat with no tools blocks", run_hook(dup, REPORT_A, state), want_block=True)
        check("second identical repeat does not block again", run_hook(dup, REPORT_A, state), want_block=False)

        ledger = state / "duplicate-turn-s1.tsv"
        if ledger.is_file():
            print("ok ledger recorded")
        else:
            failures.append("ledger file missing after block")

        diff = write_transcript(root / "d2.jsonl", final_reply=REPORT_B)
        check("different reply passes", run_hook(diff, REPORT_B, state, session="s2"), want_block=False)

        tools = write_transcript(root / "d3.jsonl", final_reply=REPORT_A, final_tools=True)
        check("identical reply after tool runs passes", run_hook(tools, REPORT_A, state, session="s3"), want_block=False)

        short_lines = [
            _user("hi"),
            _reply("ok, done"),
            _user("go on"),
            _reply("ok, done"),
        ]
        short = root / "d4.jsonl"
        short.write_text("\n".join(short_lines) + "\n")
        check("short identical status passes", run_hook(short, "ok, done", state, session="s4"), want_block=False)

        check(
            "kill switch disables the breaker",
            run_hook(dup, REPORT_A, state, session="s5", off=True),
            want_block=False,
        )

    return finish(failures)


def finish(failures: list[str]) -> int:
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        return 1
    print("all duplicate-turn-breaker checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
