#!/bin/sh
# board-wake.sh: asyncRewake hook (SessionStart, Stop) that wakes an idle
# Claude Code session when an agentmux board post lands for it.
#
# Fail-open by construction. It exits 2 (the wake) only when BOTH hold:
#   1. `agentmux board wait` exited 2, and
#   2. its stdout starts with the marker line "AGENTMUX-WAKE v1 <msgid>".
# Every other outcome exits 0: missing binary, failed or hung probe, probe
# mismatch (an older binary without `board wait`), error exit, timeout,
# garbage output, a marker on a non-2 exit. It depends only on
# `agentmux board wait --probe` and `agentmux board wait`.

PROBE_REPLY="agentmux-board-wait/1"
WAKE_MARKER="AGENTMUX-WAKE v1 "
PROBE_TIMEOUT_SECONDS=2
WAKE_EXIT=2

# The omp bridge runs `agent-hooks Stop` synchronously and cannot act on exit 2, so a
# long-poll here only stalls the Stop gate until omp's 30 s handler timeout kills it.
[ -n "$AGENT_HOOKS_HOST" ] && exit 0

command -v agentmux >/dev/null 2>&1 || exit 0

scratch=$(mktemp -d 2>/dev/null) || exit 0
trap 'rm -rf "$scratch"' EXIT

# probe_output runs `agentmux board wait --probe`, killing it after
# PROBE_TIMEOUT_SECONDS, and prints its stdout.
probe_output() {
  agentmux board wait --probe >"$scratch/probe" 2>/dev/null </dev/null &
  probe_pid=$!
  (
    sleep "$PROBE_TIMEOUT_SECONDS"
    kill "$probe_pid" 2>/dev/null
  ) >/dev/null 2>&1 &
  watchdog_pid=$!
  wait "$probe_pid" 2>/dev/null || return 1
  kill "$watchdog_pid" 2>/dev/null
  cat "$scratch/probe"
}

[ "$(probe_output)" = "$PROBE_REPLY" ] || exit 0

payload=$(cat)
output=$(printf '%s' "$payload" | agentmux board wait --session-from-stdin 2>/dev/null)
status=$?

[ "$status" -eq "$WAKE_EXIT" ] || exit 0
case "$output" in
"$WAKE_MARKER"*) ;;
*) exit 0 ;;
esac

printf '%s\n' "$output" | sed 1d >&2
exit "$WAKE_EXIT"
