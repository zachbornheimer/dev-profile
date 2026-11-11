#!/usr/bin/env bash
# probe-build.sh assembles the branch list CI actually configures: the
# .omp-build/ directory on fork/main — one TOML file per carried branch under
# .omp-build/branches/, resolved by that same commit's
# .omp-build/resolve-branches.ts. This fixture builds a throwaway oh-my-pi
# checkout whose fork remote carries that layout, so the probe must read
# the directory or die. It proves: the configured branches merge in
# order, --drop leaves a branch out, and --add of a branch missing from the
# fork fails naming it. Everything is local: origin and fork are bare repos
# under the work dir.
# Usage: probe-build-fixture.sh [probe-build.sh]
set -euo pipefail

# Hermetic: the throwaway repos must not inherit this machine's global git
# config (commit hooks, default branch, template hooks).
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
# Hermetic, part two: no global identity either, so every commit here and the
# probe's own `git commit-tree` carries this fixed one instead of dying on
# "unable to auto-detect email address".
export GIT_AUTHOR_NAME="probe-build fixture"
export GIT_AUTHOR_EMAIL="fixture@example.invalid"
export GIT_COMMITTER_NAME="probe-build fixture"
export GIT_COMMITTER_EMAIL="fixture@example.invalid"

probe="${1:-$(cd "$(dirname "$0")/.." && pwd)/agents/available-skills/updating-oh-my-pi/scripts/probe-build.sh}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$work"' EXIT

fail() {
	echo "FAIL probe-build fixture: $*" >&2
	exit 1
}

command -v bun >/dev/null 2>&1 || fail "bun is required"
[ -x "$probe" ] || bash -n "$probe" 2>/dev/null || fail "cannot read $probe"

# The fork's resolver, verbatim in contract: the probe must run the fork's own
# parser, so the fake fork carries a resolver that reads the same directory
# the real one does — .omp-build/branches/*.toml next to the script — so the
# fixture never depends on the probe setting env or cwd.
resolver="$work/resolve-branches.ts"
cat >"$resolver" <<'RESOLVER'
#!/usr/bin/env bun
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
// One TOML file per branch: the path under branches/, minus .toml, is the
// branch name. Fields: layer (integer merge order, lower first), reason.
// A minimal stand-in for the fork's parser, reading the same directory the
// real resolver treats as the single source of truth.
const branchesDir = join(dirname(import.meta.url.replace("file://", "")), "branches");
const entries: string[] = [];
const walk = (dir: string, prefix: string): void => {
	for (const entry of readdirSync(dir, { withFileTypes: true })) {
		if (entry.isDirectory()) {
			walk(join(dir, entry.name), `${prefix}${entry.name}/`);
		} else if (entry.name.endsWith(".toml")) {
			entries.push(`${prefix}${entry.name.slice(0, -".toml".length)}`);
		}
	}
};
walk(branchesDir, "");
type Entry = { branch: string; layer: number; reason: string };
const parsed: Entry[] = entries.map((branch) => {
	const raw = readFileSync(join(branchesDir, `${branch}.toml`), "utf8");
	const layer = /^layer\s*=\s*(\d+)\s*$/m.exec(raw);
	const reason = /^reason\s*=\s*"(.*)"\s*$/m.exec(raw);
	if (reason === null) throw new Error(`branches/${branch}.toml: missing a \`reason\``);
	return { branch, layer: layer === null ? 50 : Number(layer[1]), reason: reason[1] };
});
parsed.sort((a, b) => (a.layer - b.layer) || (a.branch < b.branch ? -1 : a.branch > b.branch ? 1 : 0));
for (const entry of parsed) console.log(entry.branch);
RESOLVER

# Bare remotes: origin holds main (the upstream base); fork holds main (the
# upstream base plus one carry commit: .omp-build and the workflow) plus the
# two carried branches.
origin="$work/origin.git"
fork="$work/fork.git"
git init -q --bare "$origin"
git init -q --bare "$fork"

seed="$work/seed"
git init -q -b main "$seed"
git -C "$seed" commit -q --allow-empty -m base
git -C "$seed" remote add origin "$origin"
git -C "$seed" push -q origin main
base="$(git -C "$seed" rev-parse HEAD)"

# The fork's main: upstream base plus one carry commit, touching only the
# paths probe-build.sh allows (.omp-build/ and the omp-build workflow).
git -C "$seed" remote add fork "$fork"
git -C "$seed" checkout -q -b fork-main
mkdir -p "$seed/.omp-build/branches/feat" "$seed/.github/workflows" "$seed/.github"
cp "$resolver" "$seed/.omp-build/resolve-branches.ts"
cat >"$seed/.omp-build/branches/feat/one.toml" <<'TOML'
layer = 50
reason = "Fixture branch one."
TOML
cat >"$seed/.omp-build/branches/feat/two.toml" <<'TOML'
layer = 50
reason = "Fixture branch two."
TOML
cat >"$seed/.github/workflows/omp-build.yml" <<'WORKFLOW'
jobs:
  assemble: {}
WORKFLOW
git -C "$seed" add -A
git -C "$seed" commit -q -m "carry: omp-build assembly"
git -C "$seed" push -q fork fork-main:main

# The carried branches, off the upstream base.
git -C "$seed" checkout -q -b feat/one "$base"
printf 'one\n' >"$seed/one.txt"
git -C "$seed" add -A && git -C "$seed" commit -q -m one
git -C "$seed" push -q fork feat/one
git -C "$seed" checkout -q -b feat/two "$base"
printf 'two\n' >"$seed/two.txt"
git -C "$seed" add -A && git -C "$seed" commit -q -m two
git -C "$seed" push -q fork feat/two

# The checkout the probe runs in, with both remotes configured.
checkout="$work/checkout"
git init -q "$checkout"
git -C "$checkout" remote add origin "$origin"
git -C "$checkout" remote add fork "$fork"

out="$(bash "$probe" --repo "$checkout")" || fail "probe failed on the manifest list: $out"
printf '%s\n' "$out" | grep -q '^upstream base ' || fail "no upstream base line: $out"
printf '%s\n' "$out" | grep -q '  clean    feat/one' || fail "feat/one missing: $out"
printf '%s\n' "$out" | grep -q '  clean    feat/two' || fail "feat/two missing: $out"
printf '%s\n' "$out" | grep -q '^assembly clean: 2 branches' || fail "wrong summary: $out"

out="$(bash "$probe" --repo "$checkout" --drop feat/two)" || fail "probe failed with --drop: $out"
printf '%s\n' "$out" | grep -q 'feat/two' && fail "--drop left feat/two in: $out"
printf '%s\n' "$out" | grep -q '^assembly clean: 1 branches' || fail "--drop summary wrong: $out"

rc=0
out="$(bash "$probe" --repo "$checkout" --add feat/not-pushed 2>&1)" || rc=$?
[ "$rc" = 1 ] || fail "--add of a missing branch exited $rc, not 1: $out"
printf '%s\n' "$out" | grep -q 'MISSING  feat/not-pushed' || fail "no MISSING line for feat/not-pushed: $out"

echo "probe-build fixture: ok"
