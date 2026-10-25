"""command_signature(): two commands that share only shell boilerplate
(a leading `set -euo pipefail` line) must not collide on signature.
"""

from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR / "lib"))

from hook_common.signature import command_signature

COMMIT_COMMAND = "set -euo pipefail\nR=... git -C $R commit -m 'msg'"
CHEZMOI_COMMAND = "set -euo pipefail\nchezmoi re-add ~/.agents"


def test_shared_set_preamble_does_not_collide_unrelated_commands() -> None:
    assert command_signature(COMMIT_COMMAND) != command_signature(CHEZMOI_COMMAND)


def test_leading_set_line_is_stripped_from_signature() -> None:
    assert command_signature("set -euo pipefail\ngo test ./...") == "go test ./..."
