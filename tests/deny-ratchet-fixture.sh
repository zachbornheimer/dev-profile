#!/usr/bin/env bash
# dev-profile-cargo-deny-ratchet: a finding on a crate the base lock already
# carries is inherited and must pass; a finding on a crate the push introduces
# must fail; a push that changes deny policy owns every finding. Real cargo and
# cargo-deny, offline: dependency-free crates, so the advisory database has
# nothing to say.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd -P)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL deny-ratchet fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "${GIT_CONFIG_GLOBAL}" user.name fixture
git config --file "${GIT_CONFIG_GLOBAL}" user.email fixture@example.invalid
git config --file "${GIT_CONFIG_GLOBAL}" commit.gpgsign false

mkdir -p "${work}/repo/src"
cd "${work}/repo"
git init -q -b main .
crate() { # <version> <license>; relocks the one-crate workspace in this repo
	printf '[package]\nname = "copyleft"\nversion = "%s"\nedition = "2024"\nlicense = "%s"\n' "$1" "$2" >Cargo.toml
	printf 'fn main() {}\n' >src/main.rs
	cargo generate-lockfile --offline >"${work}/output.txt" 2>&1 || fail "$1: could not lock the crate"
}
commit_all() {
	git add -A
	git commit -q -m "$1"
}

ratchet() {
	"${repo}/bin/dev-profile-cargo-deny-ratchet" "$@" >"${work}/output.txt" 2>&1
}

# The default branch already carries a copyleft crate: its finding is the
# base's debt, not a push's.
crate 0.1.0 GPL-3.0-only
commit_all "base: a copyleft crate the default branch carries"
git update-ref refs/remotes/origin/main HEAD

# A push that re-touches the lock without changing the crate inherits it.
ratchet Cargo.lock || fail "an inherited finding must pass"
grep -q "all 1 finding(s) inherited" "${work}/output.txt" ||
	fail "the inherited finding must be explained: $(cat "${work}/output.txt")"

# A push that introduces a new crate version owns its finding.
crate 0.2.0 GPL-3.0-only
commit_all "bump the copyleft crate"
if ratchet Cargo.toml Cargo.lock; then fail "a finding on an introduced crate must fail"; fi
grep -qE 'error\[(rejected|unapproved-license)\]' "${work}/output.txt" ||
	fail "the introduced finding must be reported: $(cat "${work}/output.txt")"
grep -q "1 finding(s) on crates this push introduces" "${work}/output.txt" ||
	fail "the introduced finding must be counted: $(cat "${work}/output.txt")"

# A push that changes deny policy owns the whole verdict, inherited or not.
printf '[advisories]\nversion = 2\n\n[licenses]\nversion = 2\nallow = ["MIT"]\n' >deny.toml
commit_all "tighten the license policy"
if ratchet deny.toml; then fail "a policy change must own every finding"; fi
grep -q "deny policy introduced" "${work}/output.txt" ||
	fail "the policy change must be explained: $(cat "${work}/output.txt")"

# A push that introduces no Cargo or deny file never reaches the ratchet; a
# direct call with no files is a no-op.
ratchet || fail "no introduced files must be a no-op"

echo "ok deny-ratchet fixture"
