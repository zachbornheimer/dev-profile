#!/usr/bin/env bash
# probe-build.sh assembles the branch list CI actually configures: the
# BRANCH_MANIFEST block in fork/ci:.github/workflows/omp-build.yml, resolved
# by the omp repo's own scripts/omp-build/resolve-branches.ts. This fixture
# builds a throwaway oh-my-pi checkout whose fork remote carries that workflow
# (and the retired omp-rebuild.toml with no branches key, as on the real
# fork), so the probe must read the manifest or die. It proves: the configured
# branches merge in order, --drop leaves a branch out, and --add of a branch
# missing from the fork fails naming it. Everything is local: origin and fork
# are bare repos under the work dir.
# Usage: probe-build-fixture.sh [probe-build.sh]
set -euo pipefail

# Hermetic: the throwaway repos must not inherit this machine's global git
# config (commit hooks, default branch, template hooks).
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

probe="${1:-$(cd "$(dirname "$0")/.." && pwd)/agents/available-skills/updating-oh-my-pi/scripts/probe-build.sh}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$work"' EXIT

fail() {
	echo "FAIL probe-build fixture: $*" >&2
	exit 1
}

command -v bun >/dev/null 2>&1 || fail "bun is required"
[ -x "$probe" ] || bash -n "$probe" 2>/dev/null || fail "cannot read $probe"

# The fork's resolver, verbatim: the probe must run the fork's own parser,
# so the fake fork carries the same script the real one does.
resolver="$work/resolver.ts"
cat >"$resolver" <<'RESOLVER'
#!/usr/bin/env bun
const override = process.argv[2] ?? "";
const event = process.argv[3] ?? "workflow_dispatch";
type Entry = { branch: string; reason: string };
function parseManifest(raw: string): string[] {
	const source = raw.trim();
	if (source.length === 0) {
		throw new Error("BRANCH_MANIFEST is empty");
	}
	const parsed = JSON.parse(source) as unknown;
	if (!Array.isArray(parsed)) {
		throw new Error("BRANCH_MANIFEST must be a JSON array");
	}
	return parsed.map((rawEntry, index) => {
		const entry = rawEntry as Partial<Entry>;
		if (typeof entry?.branch !== "string" || entry.branch.trim().length === 0) {
			throw new Error(`BRANCH_MANIFEST[${index}]: missing a \`branch\` name`);
		}
		if (typeof entry?.reason !== "string" || entry.reason.trim().length === 0) {
			throw new Error(`BRANCH_MANIFEST[${index}] (${entry.branch}): missing a \`reason\``);
		}
		return entry.branch.trim();
	});
}
function parseOverride(raw: string): string[] {
	return raw.split(",").map((e) => e.trim()).filter((e) => e.length > 0);
}
const branches =
	event === "workflow_dispatch" && override.trim().length > 0
		? parseOverride(override)
		: parseManifest(process.env.BRANCH_MANIFEST ?? "");
console.log(branches.join("\n"));
RESOLVER

# Bare remotes: origin holds main (the upstream base); fork holds ci (the
# workflow, the pin, the resolver, and the retired toml) plus two branches.
origin="$work/origin.git"
fork="$work/fork.git"
git init -q --bare "$origin"
git init -q --bare "$fork"

seed="$work/seed"
git init -q -b main "$seed"
git -C "$seed" -c user.email=t@t -c user.name=t commit -q --allow-empty -m base
git -C "$seed" remote add origin "$origin"
git -C "$seed" push -q origin main
base="$(git -C "$seed" rev-parse HEAD)"

git -C "$seed" remote add fork "$fork"
git -C "$seed" checkout -q -b ci
mkdir -p "$seed/.github/workflows" "$seed/scripts/omp-build" "$seed/.github"
cp "$resolver" "$seed/scripts/omp-build/resolve-branches.ts"
printf 'This file no longer holds the branch list.\n' >"$seed/.github/omp-rebuild.toml"
printf '%s\n' "$base" >"$seed/.github/omp-upstream.txt"
cat >"$seed/.github/workflows/omp-build.yml" <<'WORKFLOW'
jobs:
  assemble:
    env:
      BRANCH_MANIFEST: |
        [
          {
            "branch": "feat/one",
            "reason": "Fixture branch one."
          },
          {
            "branch": "feat/two",
            "reason": "Fixture branch two."
          }
        ]
WORKFLOW
git -C "$seed" add -A
git -C "$seed" -c user.email=t@t -c user.name=t commit -q -m ci
git -C "$seed" push -q fork ci
git -C "$seed" checkout -q -b feat/one
printf 'one\n' >"$seed/one.txt"
git -C "$seed" add -A && git -C "$seed" -c user.email=t@t -c user.name=t commit -q -m one
git -C "$seed" push -q fork feat/one
git -C "$seed" checkout -q ci
git -C "$seed" checkout -q -b feat/two
printf 'two\n' >"$seed/two.txt"
git -C "$seed" add -A && git -C "$seed" -c user.email=t@t -c user.name=t commit -q -m two
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
