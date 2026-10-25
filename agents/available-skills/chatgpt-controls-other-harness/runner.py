#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from chatgpt_control_claude.runner import run_request_file

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} request-<uuid>.json", file=sys.stderr)
        raise SystemExit(2)
    run_request_file(Path(sys.argv[1]))
    raise SystemExit(0)
