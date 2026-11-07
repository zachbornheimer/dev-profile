#!/usr/bin/env bash
# probe-build.sh reads the branch list CI actually configures: the TOML files
# under .omp-build/branches/ on fork/main, resolved by the fork's own
# .omp-build/resolve-branches.ts. This fixture builds a throwaway oh-my-pi
# checkout whose fork remote carries main = upstream base + one carry commit
# (a miniature resolver and two branch files), so the probe must read the
# directory or die. It proves: the configured branches merge in order, --drop
# leaves a branch out, and --add of a branch missing from the fork fails
# naming it. Everything is local: origin and fork are bare repos under the
# work dir.
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

# A miniature of the fork's resolver: same contract (one branch name per line
# from .omp-build/branches/**/*.toml, path minus .toml, ordered by (layer,
# path)), without the full validation.
resolver="$work/resolver.ts"
cat >"$resolver" <<'RESOLVER'
#!/usr/bin/env bun
import * as fs from "node:fs";
import * as path from "node:path";
const root = path.join(import.meta.dir, "branches");
const files: string[] = [];
const walk = (dir: string) => {
	for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
		const p = path.join(dir, e.name);
		if (e.isDirectory()) walk(p);
		else if (e.name.endsWith(".toml")) files.push(p);
	}
};
walk(root);
const entries = files.map((f) => {
	const text = fs.readFileSync(f, "utf8");
	const layer = Number(/^layer\s*=\s*(\d+)/m.exec(text)?.[1] ?? 50);
	const branch = path.relative(root, f).replace(/\.toml$/, "");
	if (!/^reason\s*=/m.test(text)) throw new Error(`${f}: missing reason`);
	return { branch, layer, file: f };
});
entries.sort((a, b) => a.layer - b.layer || (a.file < b.file ? -1 : 1));
console.log(entries.map((e) => e.branch).join("\n"));
RESOLVER

# Bare remotes: origin holds main (the upstream base); fork holds main (base
# plus the carry commit) and two branches.
origin="$work/origin.git"
fork="$work/fork.git"
git init -q --bare "$origin"
git init -q --bare "$fork"

seed="$work/seed"
git init -q -b main "$seed"
git -C "$seed" commit -q --allow-empty -m base
git -C "$seed" remote add origin "$origin"
git -C "$seed" push -q origin main

git -C "$seed" remote add fork "$fork"
mkdir -p "$seed/.omp-build/branches/feat"
cp "$resolver" "$seed/.omp-build/resolve-branches.ts"
printf 'reason = "Fixture branch one."\n' >"$seed/.omp-build/branches/feat/one.toml"
printf 'reason = "Fixture branch two."\n' >"$seed/.omp-build/branches/feat/two.toml"
git -C "$seed" add -A
git -C "$seed" commit -q -m "carry: build machinery"
git -C "$seed" push -q fork main
git -C "$seed" checkout -q -b feat/one
printf 'one\n' >"$seed/one.txt"
git -C "$seed" add -A && git -C "$seed" commit -q -m one
git -C "$seed" push -q fork feat/one
git -C "$seed" checkout -q main
git -C "$seed" checkout -q -b feat/two
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
