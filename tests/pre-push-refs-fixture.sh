#!/usr/bin/env bash
# A pre-push that cannot see the pushed refs must refuse, not judge the whole
# repository. hk bounds a step's candidate files from the refs on its stdin;
# handed none it selects every tracked file, and the steps then run their tools
# across the tree. A push that reached the hook without refs scanned this
# repository's Ruby fixtures with a tool that has nothing to do with the push.
#
# Five cases: refs the hook cannot read at all (none, or malformed), which it
# refuses; a first push to an empty remote, where no base exists to measure an
# introduced set against and hk's candidates stand in; a push against a fetched
# upstream, which must judge exactly what it introduces; and a push to an unborn
# remote branch, which the refusal must not reach.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL pre-push-refs: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

# The profile's scripts are recorded executable, but a fresh worktree checks
# them out without the bit: the installed copies under ~/.local/share would then
# win the PATH and this fixture would judge those instead of this tree. Stage
# this repository's own scripts and run them.
mkdir -p "${scratch}/bin"
cp "${repo}"/bin/dev-profile-* "${scratch}/bin/"
chmod +x "${scratch}"/bin/*

# The profile's hk config, active the way bootstrap links it, driven through the
# real pre-push path (dev-profile-pre-push). Only the steps this fixture judges
# run, and each reports the file set it was handed, so no other step's verdict
# on the fixture's files can decide the result.
mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
steps="-S newlines -S private-keys -S trailing-whitespace"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH=1 PATH="%s:${PATH}" dev-profile-pre-push %s\n' \
	"${scratch}/bin" "${steps}" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE DEV_PROFILE_PUSH_REFS DEV_PROFILE_PUSH_INTRODUCED

hook() { # <stdin-file> [args...]
	local stdin_file="$1"
	shift
	(cd "${scratch}/work" && PATH="${scratch}/bin:${PATH}" DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH=1 \
		dev-profile-pre-push "$@") <"${stdin_file}" >"${scratch}/push.txt" 2>&1
}

git init -q --bare "${scratch}/remote.git"
git init -q -b main "${scratch}/work"
git -C "${scratch}/work" remote add origin "${scratch}/remote.git"
printf 'hello\n' >"${scratch}/work/a.txt"
printf 'world\n' >"${scratch}/work/b.txt"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "feat: first file"

# 1. No refs on stdin: the pushed set is unknowable, so refuse rather than let
# hk fall back to every tracked file.
: >"${scratch}/empty"
if hook "${scratch}/empty" ${steps}; then
	fail "a hook handed no push refs must refuse the push"
fi
grep -q 'refusing the push' "${scratch}/push.txt" || fail "the refusal must say what it refused on"
if grep -q 'Fetching files' "${scratch}/push.txt"; then
	fail "no step may run when the pushed refs are unknown"
fi

# 2. A ref line git cannot produce.
printf 'refs/heads/main not-a-sha refs/heads/main not-a-sha\n' >"${scratch}/malformed"
if hook "${scratch}/malformed" ${steps}; then
	fail "a malformed ref line must refuse the push"
fi
grep -q 'refusing the push' "${scratch}/push.txt" || fail "the refusal must name the unparsable refs"

# 3. The first push of a branch to an empty remote. Its remote ref is unborn, so
# there is no base to measure an introduced set against: hk's own candidates stand
# in, nothing is refused, and the selected steps still run.
(cd "${scratch}/work" && git push -q origin main) >"${scratch}/push.txt" 2>&1 ||
	fail "a first push to an empty remote must pass"
grep -q '✔ newlines' "${scratch}/push.txt" ||
	fail "the selected steps must judge the files the push carries"
if grep -q 'refusing the push' "${scratch}/push.txt"; then
	fail "a real push must not be refused"
fi

# 4. Against a fetched upstream the hook judges exactly what the push introduces: a
# key already on the branch, pushed with the hook disabled so it landed on the
# remote, is not this push's business. A push that touches only a.txt must pass, and
# private-keys must still run on what the push does introduce.
git -C "${scratch}/work" fetch -q origin
printf -- '-----BEGIN RSA PRIVATE KEY-----\nMIIfixture\n-----END RSA PRIVATE KEY-----\n' >"${scratch}/work/.deploy-key"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "feat: key on the branch"
(cd "${scratch}/work" && GIT_CONFIG_GLOBAL=/dev/null git push -q origin main) ||
	fail "the fixture's setup push must land the key on the remote"
printf 'world\n' >>"${scratch}/work/a.txt"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "feat: second file"
(cd "${scratch}/work" && git push -q origin main) >"${scratch}/push.txt" 2>&1 ||
	fail "a push that leaves the key where it was must pass"
grep -q '✔ private-keys' "${scratch}/push.txt" ||
	fail "the private-keys step must run on what the push introduces"

# 5. A branch whose remote ref is unborn still pushes: its refs are readable, so
# the refusal above must not reach it.
(cd "${scratch}/work" && git push -q origin main:copy) >"${scratch}/push.txt" 2>&1 ||
	fail "a push to an unborn remote branch must pass"
if grep -q 'refusing the push' "${scratch}/push.txt"; then
	fail "an unborn remote ref must not be refused"
fi

echo "ok pre-push-refs"
