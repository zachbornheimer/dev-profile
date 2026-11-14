#!/usr/bin/env bash
# `wt land` routing, and `wt tree-for-changes` moving a dirty tree onto a uuid
# worktree. Dry-run covers the choice. The move is a real stash and switch in
# a temp repo; it does not commit.
# Usage: land-alias-fixture.sh [generated-dir]; no argument reads this checkout.
set -euo pipefail

out="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
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

has "default branch" "wt tree-for-changes -- wt land" "${work}/default" land
lacks "default branch follow-up uses the default" "wt land --landing" "${work}/default" land
lacks "default branch ignores --landing" "wt pr-auto" "${work}/default" land -- --landing=pr
has "force merge" "wt merge" "${work}/other" land -- --landing=merge
has "force merge skips a clean commit" "git diff --quiet" "${work}/other" land -- --landing=merge
lacks "force merge" "wt pr-auto" "${work}/other" land -- --landing=merge
has "force pr" "wt pr-auto" "${work}/personal" land -- --landing=pr
lacks "force pr" "wt merge" "${work}/personal" land -- --landing=pr
has "bad landing" "wt land: --landing must be merge or pr" "${work}/personal" land -- --landing=nope
has "https personal defaults to pr-auto" "wt pr-auto" "${work}/personal" land
lacks "https personal defaults to pr-auto" "wt merge" "${work}/personal" land
has "ssh personal defaults to pr-auto" "wt pr-auto" "${work}/personal-ssh" land
lacks "ssh personal defaults to pr-auto" "wt merge" "${work}/personal-ssh" land
# pr-auto is an alias for `wt switch ... -x dev-profile-pr`; a flag like --stage is rejected by wt switch.
lacks "pr-auto takes no flags" "wt pr-auto --" "${work}/personal" land
lacks "pr-auto takes no flags (force pr)" "wt pr-auto --" "${work}/other" land -- --landing=pr
has "https other" "wt pr-auto" "${work}/other" land
lacks "https other" "wt merge" "${work}/other" land
has "ssh other" "wt pr-auto" "${work}/other-ssh" land
has "commit-unstaged" "wt tree-for-changes -- wt land --landing=merge" "${work}/other" commit-unstaged
has "tree bare" 'wt switch --create "$id" -x git -- stash pop "$stash_ref"' "${work}/other" tree-for-changes
lacks "tree bare" "--no-cd -x sh" "${work}/other" tree-for-changes
has "tree follow-up" "--no-cd -x sh -- -c 'git stash pop \"\$1\" && shift && exec" "${work}/other" tree-for-changes -- wt land --landing=merge
has "sync loop" "until wt-sync -u -p; do" "${work}/other" sync -- -u -p
has "sync branch switch" 'wt -y switch "feat/other" --no-cd -x pwd' "${work}/other" sync -- --branch=feat/other -u -p
has "sync branch omp prompt" "Please get branch feat/other clean and rebased so 'wt-sync -u -p' succeeds" "${work}/other" sync -- --branch=feat/other -u -p

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
# Real run: land --landing=merge commits the tracked modification and never sweeps
# the untracked file into it; the alias names what it left alone.
scratch="${work}/scratch"
init_repo "${scratch}" feature "https://github.com/zachbornheimer/example.git"
printf 'tracked\n' >"${scratch}/tracked.txt"
git -C "${scratch}" add tracked.txt
git -C "${scratch}" commit -q -m "feat: tracked"
printf 'modified\n' >>"${scratch}/tracked.txt"
printf 'draft\n' >"${scratch}/untracked.txt"
land_out="$(PATH="${work}/bin:${PATH}" XDG_CONFIG_HOME="${work}/xdg" wt -y --config "${cfg}" -C "${scratch}" land --landing=merge 2>&1)" ||
	fail "land --landing=merge failed: ${land_out}"
[[ "$(git -C "${scratch}" show main:tracked.txt)" == "tracked"$'\n'"modified" ]] ||
	fail "land --landing=merge did not commit the tracked modification, main: $(git -C "${scratch}" show main:tracked.txt 2>&1)"
if git -C "${scratch}" cat-file -e main:untracked.txt 2>/dev/null; then
	fail "land --landing=merge committed untracked.txt into main"
fi
[[ -f "${scratch}/untracked.txt" ]] ||
	fail "land --landing=merge removed untracked.txt from disk"
grep -F -q "untracked.txt" <<<"${land_out}" ||
	fail "land --landing=merge did not report the untracked file it left alone, got: ${land_out}"

# Clean tree with an unrelated stash already on the stack: there is nothing to
# move, so the alias must not create a worktree and must leave that stash, and
# every ref, exactly as it found them. Before the fix the pop took whatever was
# on top of the stack and applied it in a fresh uuid worktree.
clean="${work}/clean"
init_repo "${clean}" main "https://github.com/zachbornheimer/example.git"
printf 'kept\n' >"${clean}/kept.txt"
git -C "${clean}" add kept.txt
git -C "${clean}" commit -q -m "feat: kept"
printf 'stashed\n' >>"${clean}/kept.txt"
git -C "${clean}" stash push -q -u -m "pre-existing unrelated stash"
refs_before="$(git -C "${clean}" for-each-ref --format='%(refname) %(objectname)')"
worktrees_before="$(git -C "${clean}" worktree list --porcelain | grep -c '^worktree ' || true)"
clean_out="$(PATH="${work}/bin:${PATH}" XDG_CONFIG_HOME="${work}/xdg" wt -y --config "${cfg}" -C "${clean}" tree-for-changes 2>&1)" ||
	fail "tree-for-changes on a clean tree failed: ${clean_out}"
refs_after="$(git -C "${clean}" for-each-ref --format='%(refname) %(objectname)')"
[[ "${refs_after}" == "${refs_before}" ]] ||
	fail "tree-for-changes on a clean tree moved refs (before: ${refs_before} after: ${refs_after})"
[[ "$(git -C "${clean}" worktree list --porcelain | grep -c '^worktree ' || true)" == "${worktrees_before}" ]] ||
	fail "tree-for-changes on a clean tree created a worktree"
git -C "${clean}" diff --quiet ||
	fail "tree-for-changes on a clean tree left the working tree dirty"
grep -F -q "nothing to move" <<<"${clean_out}" ||
	fail "tree-for-changes on a clean tree did not report that there was nothing to move, got: ${clean_out}"

# Real sync retry: wt-sync fails once, omp fixes the state, and the next loop
# iteration of wt-sync succeeds. Invoke the resolved wt binary directly so the
# mise shim does not prepend ~/.local/bin ahead of ${work}/bin.
real_wt="$(mise which wt)"
printf '#!/bin/sh\n[ -f "%s/sync-fixed" ] && exit 0\nexit 1\n' "${work}" >"${work}/bin/wt-sync"
printf '#!/bin/sh\nprintf "%%s\\n" "$*" >"%s/omp-args"\n: >"%s/sync-fixed"\n' "${work}" "${work}" >"${work}/bin/omp"
chmod +x "${work}/bin/wt-sync" "${work}/bin/omp"
PATH="${work}/bin:${PATH}" XDG_CONFIG_HOME="${work}/xdg" "${real_wt}" -y --config "${cfg}" -C "${work}/other" sync -- -u -p ||
	fail "wt sync retry loop did not recover after omp ran"
grep -F -q "attempt 1/5" "${work}/omp-args" ||
	fail "wt sync did not invoke omp with attempt 1/5, got: $(cat "${work}/omp-args" 2>&1)"
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
