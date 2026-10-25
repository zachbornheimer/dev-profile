#!/bin/bash
# Proves the one upstream invariant the denial-recovery hooks cannot enforce: a fresh
# Claude Code session, started from an arbitrary directory with no project .mcp.json,
# already has run_command in its tool list. When this passes there is nothing to deny
# and nothing to recover from. Run from /tmp on purpose.
set -uo pipefail

probe_dir="$(mktemp -d)"
trap 'rm -rf "$probe_dir"' EXIT

listing="$(cd "$probe_dir" && timeout 180 claude -p \
  'List the exact names of every tool you have available, one per line. Names only, no commentary.' \
  --output-format text 2>&1)"

if grep -q 'agentmux_capability_run_command' <<<"$listing"; then
  echo "run_command present in a fresh session's tool list from $probe_dir"
  exit 0
fi

echo "run_command ABSENT from a fresh session's tool list from $probe_dir" >&2
sed -n '1,30p' <<<"$listing" >&2
exit 1
