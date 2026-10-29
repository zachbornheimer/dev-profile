from __future__ import annotations

from pathlib import Path

from .protocol import new_run_id, runner_filename


def standalone_template() -> str:
    # Installed package users get a compact embedded scaffold. The repository's
    # templates/standalone_runner.py is the richer reference copy.
    return """#!/usr/bin/env python3
from pathlib import Path
import json, shutil, zipfile, traceback, datetime as dt

RUN_ID = "__RUN_ID__"
DOWNLOADS = Path.home() / "Downloads"
RUN_ROOT = Path.home() / ".chatgpt-control-claude" / "runs" / RUN_ID
TERM = RUN_ROOT / "term.out.txt"
REPORT = RUN_ROOT / "report.json"
OUT = DOWNLOADS / f"{RUN_ID}.zip"

RUN_ROOT.mkdir(parents=True, exist_ok=True)
DOWNLOADS.mkdir(parents=True, exist_ok=True)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def package(report):
    REPORT.write_text(json.dumps(report, indent=2) + "\\n")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        if TERM.exists():
            z.write(TERM, "term.out.txt")
        z.write(REPORT, "report.json")
        try:
            z.write(Path(__file__).resolve(), Path(__file__).name)
        except Exception:
            pass

def main():
    report = {"schema_version": 1, "uuid": RUN_ID, "started_at": now()}
    try:
        TERM.write_text("TODO: implement bounded local operation\\n")
        report["outcome"] = "SCAFFOLD-NOT-IMPLEMENTED"
        report["acceptance_proved"] = False
    except Exception:
        report["outcome"] = "RUNNER-FAILED"
        report["error"] = traceback.format_exc()
    finally:
        report["finished_at"] = now()
        package(report)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""


def create_runner(directory: Path) -> Path:
    run_id = new_run_id()
    path = directory / runner_filename(run_id)
    if path.exists():
        raise FileExistsError(path)
    text = standalone_template().replace("__RUN_ID__", run_id)
    compile(text, path.name, "exec")
    path.write_text(text)
    path.chmod(0o700)
    return path
