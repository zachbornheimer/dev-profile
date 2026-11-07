#!/usr/bin/env bash
# The oxlint and oxlint-fix pre-push steps hand oxlint every pushed JS/TS file. A
# push whose only JS/TS files are ones the repo's own .oxlintrc.json ignores
# (here `.omp/**`) leaves oxlint nothing to lint, and it exited 1 with "No files
# found to lint" -- a failed push for files the repo itself excludes. That push
# must pass; a push of a file the config does not ignore must still fail on its
# lint error, so the fix has not switched linting off. Real oxlint; skips when it
# is not installed.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

command -v oxlint >/dev/null 2>&1 || {
	echo "oxlint-all-ignored fixture skipped: oxlint not installed"
	exit 0
}

fail() {
	echo "FAIL oxlint-all-ignored: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

# The profile's hk config, active the way bootstrap links it, run by git's pre-push
# hook with the profile's bin directory on PATH, as home/gitconfig's hook command
# puts it. Only the two steps this fixture judges run.
mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="%s/bin:${PATH}" hk run pre-push -S oxlint -S oxlint-fix\n' \
	"${repo}" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE

work="${scratch}/work"
git init -q --bare "${scratch}/remote.git"
git init -q -b main "${work}"
git -C "${work}" remote add origin "${scratch}/remote.git"
printf '{ "ignorePatterns": [".omp/**"] }\n' >"${work}/.oxlintrc.json"
git -C "${work}" add -A
git -C "${work}" -c commit.gpgsign=false commit -qm "chore: oxlint config"
git -C "${work}" push -q origin HEAD >"${scratch}/push.txt" 2>&1 || fail "the base push must pass"

# commit_and_push <branch> <message>: the staged files, pushed under <branch>.
commit_and_push() {
	git -C "${work}" add -A
	git -C "${work}" -c commit.gpgsign=false commit -qm "$2"
	git -C "${work}" push -q origin "HEAD:refs/heads/$1" >"${scratch}/push.txt" 2>&1
}

# 1. Only a file the config ignores: oxlint has nothing to lint, and the push passes.
git -C "${work}" switch -q -c ignored-only
mkdir -p "${work}/.omp"
printf 'export const ignored = 1;\n' >"${work}/.omp/x.ts"
commit_and_push ignored-only "feat: add an ignored file" ||
	fail "a push whose only JS/TS file the oxlint config ignores must pass"

# 2. A file the config does not ignore, with a lint error: the push fails on it, and
# it fails even when an ignored file rides along.
git -C "${work}" switch -q -c lint-error main
mkdir -p "${work}/.omp"
printf 'export const ignored = 1;\n' >"${work}/.omp/x.ts"
printf 'debugger;\nexport const flawed = 1;\n' >"${work}/flawed.ts"
if commit_and_push lint-error "feat: add a flawed file"; then
	fail "a pushed file with a lint error must fail the push"
fi
grep -q 'no-debugger' "${scratch}/push.txt" || fail "the failure must be oxlint's finding in the flawed file"

echo "ok oxlint-all-ignored"
