#!/usr/bin/env bash
# The pre-push gitleaks step judges the commits a push sends, not the checkout it
# is pushed from. It used to scan `HEAD --not --remotes`: a branch push or a delete
# from a checkout whose HEAD held unrelated unpushed findings was refused (mise,
# 2026-11-17), and a pushed branch that was not HEAD was never scanned.
#
# Four cases, each a real `git push` to a local bare remote through
# dev-profile-pre-push and the profile's hk config, with real gitleaks:
#   1. HEAD holds an unpushed secret; pushing a different, clean branch passes.
#   2. HEAD holds an unpushed secret; deleting a remote branch passes.
#   3. HEAD is clean; pushing a non-HEAD branch whose new commit holds a secret fails.
#   4. Pushing HEAD with the secret fails.
# Every case runs, so one run names each case the gate gets wrong.
# Usage: gitleaks-pushed-range-fixture.sh
set -euo pipefail
command -v gitleaks >/dev/null 2>&1 || exit 0
command -v hk >/dev/null 2>&1 || exit 0

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

failures=0
bad() {
	echo "FAIL gitleaks-pushed-range: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	failures=$((failures + 1))
}

# The installed profile's scripts are on PATH; stage this repository's own and run them.
mkdir -p "${scratch}/bin" "${scratch}/hk-config"
cp "${repo}"/bin/dev-profile-* "${scratch}/bin/"
chmod +x "${scratch}"/bin/*
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH=1 PATH="%s:${PATH}" dev-profile-pre-push -S gitleaks\n' \
	"${scratch}/bin" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE DEV_PROFILE_PUSH_REFS DEV_PROFILE_PUSH_INTRODUCED

# A fake AWS access key id gitleaks' aws-access-token rule flags, assembled here so
# this file holds no match of its own.
aws_id_head="AKIA"
aws_id_tail="Q3EGW7XLMN5OPZ2R"
fake_aws_id="${aws_id_head}${aws_id_tail}"
leak_marker="leaks found"

work="${scratch}/work"
commit_on() { # <branch> <base> <file> <content> <message>: a commit on a new branch
	git -C "${work}" switch -q -c "$1" "$2"
	printf '%s\n' "$4" >"${work}/$3"
	git -C "${work}" add -A
	git -C "${work}" -c commit.gpgsign=false commit -qm "$5"
}
push() {
	(cd "${work}" && git push "$@") >"${scratch}/push.txt" 2>&1
}

git init -q --bare "${scratch}/remote.git"
git init -q -b main "${work}"
git -C "${work}" remote add origin "${scratch}/remote.git"
printf 'hello\n' >"${work}/a.txt"
git -C "${work}" add -A
git -C "${work}" -c commit.gpgsign=false commit -qm "feat: first file"
push origin main || bad "setup: the first push of a clean main must pass"
git -C "${work}" fetch -q origin

commit_on clean main clean.txt "nothing to see" "feat: clean change"
commit_on leaky main leaky.txt "aws_access_key_id = ${fake_aws_id}" "feat: leak on a side branch"
commit_on wip main wip.txt "aws_access_key_id = ${fake_aws_id}" "wip: unpushed secret"

# 1. HEAD (wip) holds an unpushed secret the push does not send.
push origin clean || bad "1: pushing a clean branch must pass though HEAD holds an unpushed secret"

# 2. A delete sends no commits. The branch it deletes is published from a clean
# HEAD first, so this case is judged on its own whatever case 1 did.
git -C "${work}" switch -q main
push origin clean || bad "setup: publishing the clean branch from a clean HEAD must pass"
git -C "${work}" switch -q wip
push origin --delete clean || bad "2: deleting a remote branch must pass though HEAD holds an unpushed secret"
if git -C "${work}" ls-remote --exit-code origin refs/heads/clean >/dev/null 2>&1; then
	bad "2: the deleted branch must be gone from the remote"
fi

# 3. The secret is on the pushed branch, not on HEAD (main, already published).
git -C "${work}" switch -q main
if push origin leaky; then
	bad "3: pushing a non-HEAD branch whose new commit holds a secret must fail"
elif ! grep -q "${leak_marker}" "${scratch}/push.txt"; then
	bad "3: the refusal must be gitleaks reporting the leak"
fi

# 4. The secret is on HEAD and HEAD is pushed.
git -C "${work}" switch -q wip
if push origin wip; then
	bad "4: pushing HEAD with a secret must fail"
elif ! grep -q "${leak_marker}" "${scratch}/push.txt"; then
	bad "4: the refusal must be gitleaks reporting the leak"
fi

[[ "${failures}" -eq 0 ]] || exit 1
echo "ok gitleaks-pushed-range"
