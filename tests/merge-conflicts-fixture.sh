#!/usr/bin/env bash
# Exercise the real global step, including hk's file selection, during a merge.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT
mkdir -p "${scratch}/config" "${scratch}/work"
ln -s "${repo}/hk/hk.pkl" "${scratch}/config/config.pkl"
export HK_CONFIG_DIR="${scratch}/config" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE
cd "${scratch}/work"
git init -q -b main
git -c commit.gpgsign=false commit --allow-empty -qm 'chore: fixture base'
git rev-parse HEAD >.git/MERGE_HEAD
hash=a82241a2833e00d5e8770cb6e43d198d22c15191
fail() {
	echo "FAIL merge-conflicts: $*" >&2
	cat "${scratch}/output" >&2
	exit 1
}
conflict() {
	mkdir -p "$(dirname "$1")"
	printf '<<<<<<<\nleft\n=======\nright\n>>>>>>>\n' >"$1"
}
check() {
	hk check -S merge-conflicts "$@" >"${scratch}/output" 2>&1
}
preimage=".fork/rr-cache/${hash}/preimage"
conflict "${preimage}"
# Control: these are real markers, not a test that passes because hk ignores them.
if hk util check-merge-conflict --assume-in-merge "${preimage}" >"${scratch}/output" 2>&1; then
	fail 'the preimage must contain detectable conflict markers'
fi
check "${preimage}" || fail 'a rerere preimage must pass the global gate'
for file in source.rs preimage ".fork/rr-cache/${hash}/postimage" ".fork/rr-cache/${hash}/source.rs" .fork/rr-cache/not-a-hash/preimage ".fork/rr-cache/${hash}a/preimage" ".fork/rr-cache/${hash:1}/preimage" "other/.fork/rr-cache/${hash}/preimage" "other/rr-cache/${hash}/preimage"; do
	conflict "${file}"
	if check "${file}"; then
		fail "source conflicts must fail: ${file}"
	fi
	grep -qi 'conflict' "${scratch}/output" || fail "failure must name the conflict: ${file}"
done
if check "${preimage}" source.rs; then
	fail 'a valid preimage must not hide a source conflict in the same invocation'
fi
printf 'resolved\n' >source.rs
check "${preimage}" source.rs || fail 'a valid preimage and clean source must pass together'
echo 'ok merge-conflicts: rerere metadata passes; source conflicts fail'
