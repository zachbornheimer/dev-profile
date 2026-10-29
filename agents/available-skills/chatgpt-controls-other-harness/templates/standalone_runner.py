#!/usr/bin/env python3
"""Reference standalone ChatGPT-controlled Grok Build runner.

Replace RUN_ID with a fresh UUID and TASK_PROMPT with the exact bounded task for
this run. The runner is self-contained so the controller can execute it directly
from ~/Downloads.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import shutil
import subprocess
import time
import traceback
import zipfile
from pathlib import Path

RUN_ID = "REPLACE-WITH-FRESH-UUID"
REPO = Path("/absolute/path/to/repo")
TASK_PROMPT = """REPLACE WITH THE EXACT, BOUNDED IMPLEMENTATION TASK."""

GROK_TIMEOUT_SECONDS = 30 * 60
GROK_MAX_TURNS = 64
GROK_WORKER_RULES = (
    "You are a bounded implementation worker controlled by ChatGPT. "
    "Follow the requested architecture and scope exactly. Inspect repository instructions "
    "before editing. Do not broaden scope or substitute a different design. Do not commit, "
    "push, merge, reset, or clean unless explicitly authorized. Run requested verification "
    "and report facts concisely."
)

DOWNLOADS = Path.home() / "Downloads"
RUN_ROOT = Path.home() / ".chatgpt-control-grok" / "runs" / RUN_ID
EVIDENCE = RUN_ROOT / "evidence"
TERM = RUN_ROOT / "term.out.txt"
REPORT = RUN_ROOT / "report.json"
OUT = DOWNLOADS / f"{RUN_ID}.zip"

RUN_ROOT.mkdir(parents=True, exist_ok=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
DOWNLOADS.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def write_evidence(relative_path: str, text: str) -> None:
    path = EVIDENCE / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def run_command(argv: list[str], relative_path: str, *, cwd: Path, timeout: int) -> int:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    write_evidence(
        relative_path,
        "$ "
        + " ".join(argv)
        + "\n"
        + f"exit_code={completed.returncode}\n\n"
        + (completed.stdout or "")
        + ("\n=== STDERR ===\n" + completed.stderr if completed.stderr else ""),
    )
    return completed.returncode


def require_provider() -> str:
    value = os.environ.get("PROVIDER", "").strip()
    if not value:
        raise RuntimeError("PROVIDER is required, e.g. PROVIDER=grok")
    return value


def harness_argv(prompt: str, *, cwd: Path) -> list[str]:
    """Run the configured coding harness as a bounded worker."""
    provider = require_provider()
    if shutil.which(provider) is None:
        raise RuntimeError(f"{provider} CLI is not on PATH")
    if provider == "grok":
        return [
            "grok",
            "--no-auto-update",
            "--cwd",
            str(cwd),
            "--output-format",
            "json",
            "--always-approve",
            "--sandbox",
            "workspace",
            "--rules",
            GROK_WORKER_RULES,
            "--no-memory",
            "--no-plan",
            "--no-subagents",
            "--disable-web-search",
            "--max-turns",
            str(GROK_MAX_TURNS),
            "-p",
            prompt,
        ]
    if provider == "claude":
        return [
            "claude",
            "--print",
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "--max-turns",
            str(GROK_MAX_TURNS),
            "-p",
            prompt,
        ]
    raise RuntimeError(f"unknown PROVIDER {provider!r}; supported: grok, claude")


def run_harness(prompt: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    argv = harness_argv(prompt, cwd=cwd)

    started = time.monotonic()
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=GROK_TIMEOUT_SECONDS,
        check=False,
    )
    write_evidence(
        "harness/run.txt",
        "$ "
        + " ".join(argv)
        + "\n"
        + f"duration_seconds={time.monotonic() - started:.3f}\n"
        + f"exit_code={completed.returncode}\n\n"
        + (completed.stdout or "")
        + ("\n=== STDERR ===\n" + completed.stderr if completed.stderr else ""),
    )
    return completed


def package(report: dict) -> None:
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    temporary = RUN_ROOT / f"{RUN_ID}.building.zip"
    if temporary.exists():
        temporary.unlink()

    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        if TERM.exists():
            archive.write(TERM, "term.out.txt")
        archive.write(REPORT, "report.json")

        for path in EVIDENCE.rglob("*"):
            if path.is_file():
                archive.write(path, str(Path("evidence") / path.relative_to(EVIDENCE)))

        with contextlib.suppress(Exception):
            archive.write(Path(__file__).resolve(), Path(__file__).name)

    shutil.copyfile(temporary, OUT)


def main() -> int:
    provider = require_provider()
    report = {
        "schema_version": 1,
        "uuid": RUN_ID,
        "executor": provider,
        "started_at": now(),
        "outcome": "NOT_STARTED",
        "acceptance_proved": False,
    }

    try:
        TERM.write_text("runner started\n")

        if not REPO.is_dir():
            raise FileNotFoundError(f"repository does not exist: {REPO}")

        run_command(
            ["git", "status", "--short"], "git/before-status.txt", cwd=REPO, timeout=30
        )
        run_command(["git", "diff", "--"], "git/before-diff.txt", cwd=REPO, timeout=30)

        harness = run_harness(TASK_PROMPT, cwd=REPO)
        if harness.returncode != 0:
            report["outcome"] = "HARNESS-FAILED"
            return 0

        # TODO: Add task-specific deterministic verification here. Only set
        # acceptance_proved=True when those checks establish the requested state.
        report["outcome"] = "IMPLEMENTED-NOT-YET-PROVED"

        run_command(
            ["git", "status", "--short"], "git/after-status.txt", cwd=REPO, timeout=30
        )
        run_command(["git", "diff", "--"], "git/after-diff.txt", cwd=REPO, timeout=30)
        run_command(
            ["git", "diff", "--name-only", "--"],
            "git/after-names.txt",
            cwd=REPO,
            timeout=30,
        )

    except subprocess.TimeoutExpired as exc:
        report["outcome"] = "RUNNER-TIMEOUT"
        report["error"] = f"command exceeded {exc.timeout}s deadline"
    except Exception:
        report["outcome"] = "RUNNER-FAILED"
        report["error"] = traceback.format_exc()
    finally:
        report["finished_at"] = now()
        with contextlib.suppress(Exception):
            package(report)

    # Deliberate: controller must receive failure evidence too.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
