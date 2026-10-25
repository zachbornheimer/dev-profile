#!/bin/sh
# Exit 0 when this hook runs for a person's own harness session; exit 1 when it runs inside a
# non-interactive model call that a hook itself started (agentmux's identify_intent calls `grok -p`,
# which starts a full grok session whose own prompt-submit hook would call agentmux again: an unbounded
# loop that spawned thousands of MCP gateways on 2026-10-14/15). Nesting is read from the environment
# marker first, then from the ancestry: any ancestor that is a single-turn harness call or an agentmux hook.
#
# Usage in a hook command:  if ~/.agents/hooks/nested-run-guard.sh; then <hook command>; fi
set -u

if [ -n "${AGENTMUX_NESTED_RUN:-}" ]; then
  exit 1
fi

NESTED_PATTERN='(^| )(grok -p|grok --single|claude -p|claude --print|codex exec|agentmux hooks run|agentmux capability run)( |$)'
MAX_DEPTH=12

pid=$$
depth=0
while [ "$depth" -lt "$MAX_DEPTH" ] && [ "$pid" -gt 1 ]; do
  pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
  [ -z "$pid" ] && break
  command=$(ps -o command= -p "$pid" 2>/dev/null)
  if printf '%s' "$command" | grep -Eq "$NESTED_PATTERN"; then
    exit 1
  fi
  depth=$((depth + 1))
done
exit 0
