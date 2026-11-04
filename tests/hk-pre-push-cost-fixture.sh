#!/usr/bin/env bash
# The whole-repository analyzers are opt-in. Every step that judges a whole
# module, workspace or app instead of the pushed diff carries
# profiles = List("slow"), so the default pre-push and check plans skip it and
# `--slow` includes it: a one-line push pays for its own diff, and CI pays for
# the repository.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL hk-pre-push-cost: $*" >&2
	exit 1
}

mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
# The machine's global hooks must not judge this fixture's scratch commits.
: >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config"
export GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE

# One file per ecosystem, so every slow step's glob matches and its profile is
# the only reason left to skip it. Cargo.lock is the workspace indicator hk
# resolves a cargo-deny job from.
files() { # <dir>
	printf 'export const answer = 1\n' >"$1/answer.ts"
	printf 'package main\n' >"$1/main.go"
	printf 'module example\n' >"$1/go.mod"
	printf '[package]\nname = "example"\n' >"$1/Cargo.toml"
	printf 'version = 3\n' >"$1/Cargo.lock"
	printf 'puts :ok\n' >"$1/app.rb"
	printf 'GEM\n  remote: https://example.invalid\n' >"$1/Gemfile.lock"
}

git init -q -b main "${scratch}/work"
printf 'base\n' >"${scratch}/work/base.txt"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "chore: base"
# The default branch is published without pushing it: the wrapper refuses a push
# of refs/heads/main.
git -C "${scratch}/work" update-ref refs/remotes/origin/main HEAD

# The pushed branch carries the files, so a pre-push plan has something to judge.
git -C "${scratch}/work" switch -q -c feature
files "${scratch}/work"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "feat: one file per ecosystem"

slow_steps="gosec go-vet golangci-lint govulncheck cargo-deny brakeman bundle-audit foxguard-typescript"

# The plan, compacted so one line carries a step's status and its reasons.
plan() { # <hook> [extra hk args...]
	local hook="$1"
	shift
	(cd "${scratch}/work" && hk run "${hook}" --plan --json "$@" 2>/dev/null) | tr -d ' \n'
}

entry() { # <compacted plan> <step>
	printf '%s' "$1" | grep -o "\"name\":\"$2\",\"status\":\"[a-z]*\".\{0,150\}" | head -n1
}

assert_status() { # <plan> <step> <expected>
	local got
	got="$(entry "$1" "$2" | sed 's/.*"status":"//; s/".*//')"
	[[ "${got}" == "$3" ]] || fail "$2 must be $3, was ${got:-absent} -- $(entry "$1" "$2")"
}

assert_profile_skips() { # <hook> <plan>
	local step
	for step in ${slow_steps}; do
		assert_status "$2" "${step}" skipped
		entry "$2" "${step}" | grep -q '"kind":"profile_exclude"' ||
			fail "$1: ${step} must be skipped for its profile -- $(entry "$2" "${step}")"
	done
}

# 1. A push: the whole-repository analyzers are skipped, and the profile is why
# -- not a glob that happened not to match.
assert_profile_skips pre-push "$(plan pre-push)"

# 2. --slow: the same steps are in the plan, so CI and a deliberate run still get
# them.
slow="$(plan pre-push -s)"
for step in ${slow_steps}; do
	assert_status "${slow}" "${step}" included
done

# 3. The check hook shares the gates, and judges the working tree: a fresh file
# per ecosystem that no commit carries.
mkdir -p "${scratch}/work/extra"
files "${scratch}/work/extra"
assert_profile_skips check "$(plan check)"

echo "ok hk-pre-push-cost fixture"
