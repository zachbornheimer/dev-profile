#!/usr/bin/env bash
# `wt land` routing, and `wt tree-for-changes` moving a dirty tree onto a uuid
# worktree. Dry-run covers the choice. The move is a real stash and switch in
# a temp repo; it does not commit.
# Usage: land-alias-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: land-alias-fixture.sh <generated-dir>}"
cfg="${out}/worktrunk.toml"
[[ -f "${cfg}" ]] || cfg="${out}/config/worktrunk.toml"
work="$(cd "$(mktemp -d)" && pwd -P)"

fail() {
	echo "FAIL land-alias fixture: $*" >&2
	exit 1
}

cleanup() { rm -rf "${work}"; }
trap cleanup EXIT

[[ -f "${cfg}" ]] || fail "missing ${cfg}"

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com

init_repo() {
	local dir="$1" branch="$2" origin="$3"
	git init -q -b main "${dir}"
	git -C "${dir}" commit -q --allow-empty -m init
	if [[ "${branch}" != main ]]; then
		git -C "${dir}" switch -q -c "${branch}"
	fi
	if [[ -n "${origin}" ]]; then
		git -C "${dir}" remote add origin "${origin}"
	fi
}

dry() {
	local dir="$1"
	shift
	wt -y --config "${cfg}" -C "${dir}" config alias dry-run "$@"
}

has() {
	local label="$1" needle="$2"
	shift 2
	local rendered
	rendered="$(dry "$@")" || fail "${label}: dry-run failed"
	if ! grep -F -q -- "${needle}" <<<"${rendered}"; then
		printf '%s\n' "${rendered}" >&2
		fail "${label}: missing ${needle}"
	fi
}

lacks() {
	local label="$1" needle="$2"
	shift 2
	local rendered
	rendered="$(dry "$@")" || fail "${label}: dry-run failed"
	if grep -F -q -- "${needle}" <<<"${rendered}"; then
		printf '%s\n' "${rendered}" >&2
		fail "${label}: unexpected ${needle}"
	fi
}

init_repo "${work}/default" main ""
init_repo "${work}/personal" feature "https://github.com/zachbornheimer/example.git"
init_repo "${work}/personal-ssh" feature "git@github.com:zachbornheimer/example.git"
init_repo "${work}/other" feature "https://github.com/ZAB-AI-LLC/example.git"
init_repo "${work}/other-ssh" feature "git@github.com:ZAB-AI-LLC/example.git"

has "default branch" "wt tree-for-changes -- wt land --landing=merge" "${work}/default" land
lacks "default branch ignores --landing" "wt pr-auto" "${work}/default" land -- --landing=pr
has "force merge" "wt merge" "${work}/other" land -- --landing=merge
has "force merge skips a clean commit" "git diff --quiet" "${work}/other" land -- --landing=merge
lacks "force merge" "wt pr-auto" "${work}/other" land -- --landing=merge
has "force pr" "wt pr-auto" "${work}/personal" land -- --landing=pr
lacks "force pr" "wt merge" "${work}/personal" land -- --landing=pr
has "bad landing" "wt land: --landing must be merge or pr" "${work}/personal" land -- --landing=nope
has "https personal" "wt merge" "${work}/personal" land
lacks "https personal" "wt pr-auto" "${work}/personal" land
has "ssh personal" "wt merge" "${work}/personal-ssh" land
has "https other" "wt pr-auto" "${work}/other" land
lacks "https other" "wt merge" "${work}/other" land
has "ssh other" "wt pr-auto" "${work}/other-ssh" land
has "commit-unstaged" "wt tree-for-changes -- wt land --landing=merge" "${work}/other" commit-unstaged
has "tree bare" 'wt switch --create "$id" -x git -- stash pop' "${work}/other" tree-for-changes
lacks "tree bare" "--no-cd -x sh" "${work}/other" tree-for-changes
has "tree follow-up" "--no-cd -x sh -- -c 'git stash pop && exec" "${work}/other" tree-for-changes -- wt land --landing=merge

# Unborn repo (no initial commit yet): bare tree-for-changes prints a helpful error,
# and commit-unstaged / land commits directly instead of calling git stash.
unborn="${work}/unborn"
git init -q -b main "${unborn}"
git -C "${unborn}" remote add origin "https://github.com/zachbornheimer/example.git"
printf 'init\n' >"${unborn}/a.txt"
unborn_err=""
if unborn_err="$(wt -y --config "${cfg}" -C "${unborn}" tree-for-changes 2>&1)"; then
	fail "bare tree-for-changes on unborn repo must fail"
fi
grep -F -q "wt commit-unstaged" <<<"${unborn_err}" ||
	fail "bare tree-for-changes on unborn repo must suggest wt commit-unstaged, got: ${unborn_err}"
! grep -F -q "You do not have the initial commit yet" <<<"${unborn_err}" ||
	fail "bare tree-for-changes on unborn repo must not print raw git stash error, got: ${unborn_err}"
mkdir -p "${work}/bin" "${work}/xdg/worktrunk"
ln -s "${cfg}" "${work}/xdg/worktrunk/config.toml"
printf '#!/bin/sh\necho "feat: initial commit"\n' >"${work}/bin/_llm"
chmod +x "${work}/bin/_llm"
XDG_CONFIG_HOME="${work}/xdg" PATH="${work}/bin:${PATH}" wt -y --config "${cfg}" -C "${unborn}" commit-unstaged
[[ "$(git -C "${unborn}" show HEAD:a.txt)" == "init" ]] ||
	fail "commit-unstaged on unborn repo did not create initial commit with a.txt"
# Real move: an untracked file leaves the invoking tree and lands on a uuid branch.
move="${work}/move"
init_repo "${move}" main "https://github.com/zachbornheimer/example.git"
printf 'pending\n' >"${move}/pending.txt"
wt -y --config "${cfg}" -C "${move}" tree-for-changes
if [[ -e "${move}/pending.txt" ]]; then
	fail "tree-for-changes left pending.txt in the invoking tree"
fi
uuid='[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
found=""
while IFS= read -r line; do
	case "${line}" in
	worktree\ *) found="${line#worktree }" ;;
	branch\ *)
		ref="${line#branch }"
		name="${ref#refs/heads/}"
		if [[ "${name}" =~ ^${uuid}$ && -f "${found}/pending.txt" ]]; then
			grep -F -q pending "${found}/pending.txt" || fail "pending.txt was not popped"
			exit 0
		fi
		;;
	esac
done < <(git -C "${move}" worktree list --porcelain)
fail "tree-for-changes did not pop pending.txt onto a uuid worktree"
