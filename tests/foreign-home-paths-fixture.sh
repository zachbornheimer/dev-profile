#!/usr/bin/env bash
# The foreign-home-paths push judge against real git: a push may not add an absolute home path, in a line or as
# a symlink target, but a file that already holds one can still be edited, and a relative target passes.
# Usage: foreign-home-paths-fixture.sh [<repo root>]
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
judge="${root}/bin/dev-profile-foreign-home-paths"

fail() {
	echo "FAIL foreign-home-paths: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
origin="${work}/origin.git"
git init -q --bare -b main "${origin}"
repo="${work}/repo"
git clone -q "${origin}" "${repo}" 2>/dev/null
cd "${repo}"
git config commit.gpgsign false
mkdir -p app docs
printf 'legacy: /home/old/tool/bin\n' >app/legacy.conf
printf 'x\n' >app/real.ts
git add -A && git commit -qm base && git push -q origin HEAD:main
git remote set-head origin main >/dev/null
git switch -q -c feature

run_judge() { "${judge}" "$@" >"${work}/output.txt" 2>&1; }
commit() { git add -A && git commit -qm "$1"; }
expect_pass() { run_judge "$@" || fail "must pass: $*"; }
expect_fail() { # <needle> <file>...
	local needle="$1"
	shift
	if run_judge "$@"; then fail "must fail: $*"; fi
	grep -Fq -- "${needle}" "${work}/output.txt" || fail "the failure must name '${needle}'"
}

# A file that already holds a literal can be edited: only added lines are judged.
printf 'legacy: /home/old/tool/bin\n# a comment\n' >app/legacy.conf
commit "edit a file that holds an old literal"
expect_pass app/legacy.conf

# An added literal fails, for either OS's home, and the failure names the line.
printf 'x\nHOME_DIR=/home/user/Developer\n' >app/real.ts
commit "add a linux home"
expect_fail "/home/user/Developer" app/real.ts
printf 'x\nHOME_DIR=/Users/someone/Developer\n' >app/real.ts
commit "add a mac home"
expect_fail "/Users/someone/Developer" app/real.ts

# Portable spellings and placeholders pass.
printf 'x\nA="$HOME/Developer"\nB=~/Developer\nC={{ env.HOME }}/d\nD=/Users/<name>/d\nE=/Users/Shared/d\n' >app/real.ts
commit "portable spellings"
expect_pass app/real.ts

# A deliberate literal carries the marker.
printf 'x\nF=/home/user/x # portable-home-ok: sandbox fixture\n' >app/real.ts
commit "marked literal"
expect_pass app/real.ts

# Prose and tests are exempt.
printf 'see /home/user/Developer\n' >docs/notes.md
commit "prose"
expect_pass docs/notes.md

# A symlink: an absolute target into a home fails, a relative target passes.
ln -s /home/user/Developer/target.ts app/abs-link.ts
ln -s ../app/real.ts app/rel-link.ts
commit "symlinks"
expect_fail "symlink to /home/user/Developer/target.ts" app/abs-link.ts
expect_pass app/rel-link.ts

# A push judged through SAH_PUSH_REFS (a new branch: remote sha all zeros) sees the same.
zeros=0000000000000000000000000000000000000000
printf 'refs/heads/feature %s refs/heads/feature %s\n' "$(git rev-parse HEAD)" "${zeros}" >"${work}/refs"
if SAH_PUSH_REFS="${work}/refs" run_judge app/abs-link.ts; then fail "an added absolute symlink must fail (SAH_PUSH_REFS)"; fi

echo "ok foreign-home-paths"
