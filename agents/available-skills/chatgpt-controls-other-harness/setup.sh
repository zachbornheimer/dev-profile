#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"

echo "repo: $ROOT"
echo "uv: $(command -v uv || true)"
echo "claude: $(command -v claude || true)"

if ! command -v uv >/dev/null 2>&1; then
	echo "error: uv is required" >&2
	exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
	echo "warning: Claude Code CLI ('claude') is not currently on PATH" >&2
fi

uv sync
uv run python -m unittest discover -s tests -v

echo
echo "Ready."
echo "Claude Code by Anthropic is invoked through the local 'claude' CLI."
echo "Give PROMPT_TO_GIVE_AGENT.md plus your task to a cloud planner/reviewer."
