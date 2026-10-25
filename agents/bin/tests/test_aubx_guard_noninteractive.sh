#!/usr/bin/env bash
# shellcheck disable=SC2034 # out and rc are read by assert's eval'd condition strings
# Proves the guard still reaches the real installer from a shell that never
# sourced the rc files. launchd, cron, a hook runner and a bare `sh -c` get a
# PATH without mise or Homebrew, so the PATH scan finds no second aubx. Before
# this test existed the guard died with 127 there: safe (nothing leaked) but no
# global skill install worked from those entry points.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
GUARD="$BIN/aubx"
AUBE="$BIN/aube"
BARE_PATH=/usr/bin:/bin
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

[ -x "$GUARD" ] || { echo "FAIL - guard missing at $GUARD"; exit 1; }

run_bare() { env -i HOME="$HOME" PATH="$BARE_PATH" TERM=dumb /bin/bash -c "$1" 2>&1; }

out="$(run_bare "$GUARD --version")"; rc=$?
assert "bare shell: aubx --version exits 0" '[ "$rc" -eq 0 ]'
assert "bare shell: aubx --version prints a version" 'case "$out" in *[0-9].[0-9]*.[0-9]*) true ;; *) false ;; esac'
assert "bare shell: no 'no real aubx' failure" 'case "$out" in *"no real aubx"*) false ;; *) true ;; esac'

# Routing stays intact where the installer was unreachable before: the refused
# verb must still name the roster and never run the installer.
out="$(run_bare "$GUARD skills sync")"; rc=$?
assert "bare shell: skills sync refuses with exit 2" '[ "$rc" -eq 2 ]'
assert "bare shell: refusal names available-skills" 'case "$out" in *available-skills*) true ;; *) false ;; esac'

out="$(run_bare "$AUBE --version")"; rc=$?
assert "bare shell: aube --version exits 0" '[ "$rc" -eq 0 ]'
assert "bare shell: aube --version prints a version" 'case "$out" in *[0-9].[0-9]*.[0-9]*) true ;; *) false ;; esac'

# The confiner resolves the installer on the same bare PATH, so an install
# routed through it fails on its own terms (not "no aubx on PATH").
out="$(run_bare "AGENTS_HOME=/nonexistent-agents-home $BIN/aubx-skills skills add example/none --skill x -g -y" 2>&1)"
assert "bare shell: confiner found the installer" 'case "$out" in *"no aubx on PATH"*) false ;; *) true ;; esac'

[ "$fail" -eq 0 ] && echo "PASS test_aubx_guard_noninteractive.sh"
exit "$fail"
