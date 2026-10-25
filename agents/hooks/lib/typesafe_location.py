"""Single source of truth for where the TypeSafe skill lives."""

from pathlib import Path

TYPESAFE_SCRIPTS_DIR = Path.home() / ".agents/available-skills/typesafe-ai/scripts"
TYPESAFE_CLI = TYPESAFE_SCRIPTS_DIR / "typesafe.py"
