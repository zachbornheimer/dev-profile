#!/usr/bin/env bash
# Pin the SKIP and FAIL branches of tests/rules-gate.sh and the exit-code
# propagation of the run branch, against scratch OMP_AGENT_DIRs (no live install).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
gate=(bash "$root/tests/rules-gate.sh")
fail() {
	cat "$scratch/output" >&2
	echo "FAIL: $*" >&2
	exit 1
}

# No install: explicit SKIP naming the path, exit 0.
OMP_AGENT_DIR="$scratch/absent" "${gate[@]}" >"$scratch/output" 2>&1 || fail "absent install must exit 0"
grep -Fq "SKIP: no omp install at $scratch/absent" "$scratch/output" || fail "absent install did not print SKIP naming the path"

# Install without its gate: non-zero, names the missing file.
mkdir -p "$scratch/bare/rules"
if OMP_AGENT_DIR="$scratch/bare" "${gate[@]}" >"$scratch/output" 2>&1; then fail "install without gate was accepted"; fi
grep -Fq "$scratch/bare/rules/rule_conditions.test.ts" "$scratch/output" || fail "missing gate did not name its path"
grep -Fq SKIP "$scratch/output" && fail "missing gate printed SKIP"

# Install with a gate: its exit code propagates, both ways.
mkdir -p "$scratch/live/rules"
cat >"$scratch/live/rules/rule_conditions.test.ts" <<'TS'
import { expect, test } from 'bun:test';
test('passes', () => expect(1).toBe(1));
TS
OMP_AGENT_DIR="$scratch/live" "${gate[@]}" >"$scratch/output" 2>&1 || fail "passing gate did not exit 0"
cat >"$scratch/live/rules/rule_conditions.test.ts" <<'TS'
import { expect, test } from 'bun:test';
test('fails', () => expect(1).toBe(2));
TS
if OMP_AGENT_DIR="$scratch/live" "${gate[@]}" >"$scratch/output" 2>&1; then fail "failing gate exited 0"; fi
echo 'ok: rules gate skips without an install, fails without its gate file, and propagates the gate exit code'
