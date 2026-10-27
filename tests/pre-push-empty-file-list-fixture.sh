#!/usr/bin/env bash
# A push whose diff holds no files must not fail the pre-push hook or scan the
# wrong tree. hk hands a step with no glob an empty {{files}}: the hk util checks
# then exit with a usage error, and `betterleaks dir` with no path scans the
# process cwd (an archive push run from `/` scanned the whole disk). Two real
# 0-file pushes: an existing commit under a new branch name, and a push from a
# bare git dir run in a directory holding a secret. A pushed private key must
# still fail, so the empty-list guard has not switched the checks off.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL pre-push-empty-file-list: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

# The profile's hk config, active the way bootstrap links it, run by git's pre-push
# hook. Only the steps this fixture judges run, so another step's verdict on the
# fixture's files cannot decide it. destroyed-symlinks takes no files: with only
# file steps selected hk stops at "no files to run", and the bug never shows.
mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
steps="-S betterleaks -S check-executables-have-shebangs -S merge-conflicts -S private-keys -S destroyed-symlinks"
# The profile's bin directory on PATH, as home/gitconfig's hook command puts it.
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="${PATH}:%s/bin" hk run pre-push %s\n' \
	"${repo}" "${steps}" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE

commit() { # <message>
	git -C "${scratch}/work" add -A
	HK=0 git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "$1"
}
push() { # <cwd> <git args...>
	local cwd="$1"
	shift
	(cd "${cwd}" && git "$@") >"${scratch}/push.txt" 2>&1
}

git init -q --bare "${scratch}/remote.git"
git init -q -b main "${scratch}/work"
git -C "${scratch}/work" remote add origin "${scratch}/remote.git"
printf 'hello\n' >"${scratch}/work/a.txt"
commit "feat: first file"
push "${scratch}/work" push -q origin main || fail "the first push of a file must pass"

# Each 0-file case first proves hk saw no files, so a pass is not a pass for another reason.
expect_empty_diff() { grep -q '(0 files)' "${scratch}/push.txt" || fail "$1: hk must have seen no pushed files"; }

# 1. The pushed commit under a new branch name: the diff against origin/main holds no files.
push "${scratch}/work" push -q origin main:copy || fail "a push with no changed files must pass"
expect_empty_diff "new branch name"

# 2. A bare git dir pushed from a directory holding a secret: no step may scan that directory.
mkdir -p "${scratch}/elsewhere"
printf "curl -H 'authorization: Bearer %s' https://api.example.invalid\n" \
	"7f3c9a1e5b2d8f4a6c0e9b3d7a1f5c8e2b4d6a9f" >"${scratch}/elsewhere/notes.sh"
if betterleaks dir --redact --no-banner "${scratch}/elsewhere" >/dev/null 2>&1; then
	fail "control: betterleaks must flag the decoy, or this case proves nothing"
fi
push "${scratch}/elsewhere" --git-dir="${scratch}/work/.git" push -q "file://${scratch}/remote.git" main:archive ||
	fail "a git-dir push must not judge the directory it was run from"
expect_empty_diff "git-dir push"

# 3. The guard has not switched the checks off: a pushed private key, in a dotfile, still fails.
git -C "${scratch}/work" switch -q -c feature
printf -- '-----BEGIN RSA PRIVATE KEY-----\nMIIfixture\n-----END RSA PRIVATE KEY-----\n' >"${scratch}/work/.deploy-key"
commit "feat: add a key"
if push "${scratch}/work" push -q origin feature; then fail "a pushed private key must fail the push"; fi
grep -q '✗ private-keys' "${scratch}/push.txt" || fail "the private-keys step must be the one that fails"

echo "ok pre-push-empty-file-list"
