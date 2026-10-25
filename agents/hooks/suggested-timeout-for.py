#!/usr/bin/env python3
"""Time one hook with hyperfine and print a JSON list of speed + run logs.

Usage:
    suggested-timeout-for.py -- <path>
    suggested-timeout-for.py --runs 20 --warmup 3 -- /path/to/hook.py
    suggested-timeout-for.py --payload event.json -- /path/to/hook.py --mode=fast

Stdout is a one-element JSON list. Each element has summary stats, a
``suggested_timeout_seconds`` equal to ceil(p95), and ``runs_log`` with
every hyperfine sample (seconds + exit_code). Stderr is hyperfine's own
progress. Isolated hook state goes to a temp dir via HC_STATE_DIR_OVERRIDE.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from suggested_timeout import (
    TimeoutReport,
    decide_timeout,
    observation_from_hyperfine,
)

DEFAULT_RUNS = 20
DEFAULT_WARMUP = 3
DEFAULT_STDIN = "{}\n"
HYPERFINE_BINARY = "hyperfine"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="suggested-timeout-for.py",
        description="Time a hook with hyperfine and print p95 timeout JSON.",
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument(
        "--payload",
        type=Path,
        default=None,
        help="JSON file piped to the hook as stdin (default: {})",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="hook path and optional args after --",
    )
    args = parser.parse_args(list(argv))
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("usage: suggested-timeout-for.py -- <path> [args...]")
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    args.hook = Path(command[0])
    args.hook_args = tuple(command[1:])
    return args


def _stdin_file(scratch: Path, payload: Path | None) -> Path:
    stdin_file = scratch / "stdin.json"
    if payload is None:
        stdin_file.write_text(DEFAULT_STDIN)
        return stdin_file
    if not payload.is_file():
        raise FileNotFoundError(f"payload is not a file: {payload}")
    stdin_file.write_bytes(payload.read_bytes())
    return stdin_file


def _timed_executable(scratch: Path, hook: Path, hook_args: tuple[str, ...]) -> Path:
    """Hyperfine --shell=none takes one argv; extra hook args go through a wrapper."""
    if not hook_args:
        return hook
    wrapper = scratch / "run-hook"
    command = " ".join(shlex.quote(part) for part in (str(hook), *hook_args))
    wrapper.write_text(f"#!/bin/sh\nexec {command}\n")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper


def observe_hook_speed(
    hook: Path,
    hook_args: tuple[str, ...],
    payload: Path | None,
    runs: int,
    warmup: int,
    env: Mapping[str, str],
    scratch: Path,
) -> TimeoutReport:
    """Run hyperfine, then decide the p95 timeout from its run logs."""
    stdin_file = _stdin_file(scratch, payload)
    export_file = scratch / "hyperfine.json"
    timed = _timed_executable(scratch, hook, hook_args)
    hyperfine = shutil.which(HYPERFINE_BINARY)
    if hyperfine is None:
        raise FileNotFoundError("hyperfine is not on PATH")
    argv = [
        hyperfine,
        "--style",
        "none",
        "--shell",
        "none",
        "--ignore-failure",
        "--warmup",
        str(warmup),
        "--runs",
        str(runs),
        "--input",
        str(stdin_file),
        "--export-json",
        str(export_file),
        str(timed),
    ]
    child_env = dict(env)
    # Time the Claude path: a Grok session would make quality-guard-run defer.
    child_env.pop("GROK_SESSION_ID", None)
    child_env.pop("QUALITY_GUARD_SOURCE", None)
    child_env["HC_STATE_DIR_OVERRIDE"] = str(scratch / "hook-state")
    (scratch / "hook-state").mkdir()
    done = subprocess.run(argv, env=child_env, check=False)
    if done.returncode != 0 or not export_file.is_file():
        raise RuntimeError(f"hyperfine exited {done.returncode} without a JSON export for {hook}")
    result = json.loads(export_file.read_text())
    results = result.get("results")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise ValueError("hyperfine JSON must contain exactly one results object")
    command = (str(hook), *hook_args)
    observation = observation_from_hyperfine(
        str(hook),
        command,
        str(payload) if payload is not None else None,
        runs,
        warmup,
        results[0],
    )
    return decide_timeout(observation)


def suggested_timeout_for(argv: Sequence[str], env: Mapping[str, str]) -> list[dict[str, object]]:
    """Product operation: observe hyperfine logs, decide p95, return JSON list."""
    args = parse_args(argv)
    hook = args.hook.expanduser()
    if not hook.is_file():
        raise FileNotFoundError(f"hook is not a file: {hook}")
    if not os.access(hook, os.X_OK):
        raise PermissionError(f"hook is not executable: {hook}")
    payload = args.payload.expanduser() if args.payload is not None else None
    with tempfile.TemporaryDirectory(prefix="suggested-timeout-") as raw_scratch:
        report = observe_hook_speed(
            hook.resolve(),
            args.hook_args,
            payload.resolve() if payload is not None else None,
            args.runs,
            args.warmup,
            env,
            Path(raw_scratch),
        )
    return [report.to_json()]


def main(argv: Sequence[str] | None = None) -> int:
    try:
        payload = suggested_timeout_for(argv if argv is not None else sys.argv[1:], os.environ)
    except argparse.ArgumentError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (FileNotFoundError, PermissionError, ValueError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
