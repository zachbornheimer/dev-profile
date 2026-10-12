#!/usr/bin/env bash
# `wt done` parks unfinished work and restacks each eligible branch onto
# origin/<default>. Real git; wt-sync and gh are stubs that log arguments.
# Usage: done-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: done-fixture.sh <generated-dir>}"
done="${out}/bin/dev-profile-done"
[[ -x "$done" ]] || {
	echo "FAIL done fixture: missing ${done}" >&2
	exit 1
}

work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL done fixture: $*" >&2
	exit 1
}

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false
# Setup commits still run prepare-commit-msg (--no-verify does not skip it).
# HK=0 is unset again before invoking done, so a missing script-level export
# still fails the hook-skip case.
export HK=0

stubs="${work}/stubs"
mkdir -p "$stubs"
export WT_LOG="${work}/wt-sync.log"
: >"$WT_LOG"
cat >"${stubs}/wt-sync" <<'STUB'
#!/usr/bin/env bash
echo "wt-sync $*" >>"${WT_LOG}"
if [[ " $* " == *" --all "* ]]; then
	exit 1
fi
exit 0
STUB
cat >"${stubs}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >>"${WT_LOG}"
if [[ "$1" == pr && "$2" == list ]]; then
	# Real gh --jq '.[0].number' on [] prints nothing.
	[[ "$*" == *--jq* ]] || echo '[]'
	exit 0
fi
exit 1
STUB
chmod +x "${stubs}"/*
export PATH="${stubs}:${PATH}"

commit() { # <repo> <file> <content>
	printf '%s\n' "$3" >"$1/$2"
	git -C "$1" add "$2"
	git -C "$1" commit --no-verify -q -m "$2: $3"
}

origin=""
repo=""
setup_clone() { # <name>
	origin="${work}/${1}.git"
	repo="${work}/${1}"
	git init -q --bare --initial-branch=main "$origin"
	git clone -q "$origin" "$repo" 2>/dev/null
	git -C "$repo" config user.email t@example.com
	git -C "$repo" config user.name t
	git -C "$repo" config commit.gpgsign false
	git -C "$repo" config dev-profile.sync-clone "$1"
	git -C "$repo" switch -q -c main
	commit "$repo" base.txt base
	git -C "$repo" push --no-verify -q origin main
	git -C "$origin" symbolic-ref HEAD refs/heads/main
	git -C "$repo" remote set-head origin main
}

run_done() {
	local dir="$1"
	shift
	: >"$WT_LOG"
	# The script under test must set HK=0; the fixture must not.
	(cd "$dir" && unset HK && "$done" "$@")
}

called_wt_sync_all() {
	grep -q -- '--all' "$WT_LOG"
}

# --- Hook skip: parking must ignore core.hooksPath quality hooks.
setup_clone park
git -C "$repo" switch -q -c feat/park
commit "$repo" tracked.txt original
printf 'dirty\n' >"${repo}/tracked.txt"
hooks="${work}/hooks"
mkdir -p "$hooks"
for hook in pre-commit pre-push; do
	cat >"${hooks}/${hook}" <<'HOOK'
#!/usr/bin/env bash
echo blocked >&2
exit 1
HOOK
	chmod +x "${hooks}/${hook}"
done
git -C "$repo" config core.hooksPath "$hooks"
run_done "$repo" --no-pr --no-prune >"${work}/park.out" 2>&1 || fail "done must park dirty work: $(cat "${work}/park.out")"
[[ "$(git -C "$repo" show feat/park:tracked.txt)" == dirty ]] || fail "the save commit must hold the dirty file"
[[ "$(git -C "$repo" log -1 --format=%s feat/park)" == "chore: save uncommitted work on feat/park" ]] ||
	fail "the save commit must use the parking message"
git -C "$origin" rev-parse --verify --quiet refs/heads/feat/park >/dev/null || fail "origin must have feat/park"
[[ "$(git -C "$origin" show feat/park:tracked.txt)" == dirty ]] || fail "origin must have the parked file"
called_wt_sync_all && fail "wt-sync --all must not be called: $(cat "$WT_LOG")"

# --- Backup is not a restack parent.
setup_clone stack
git -C "$repo" switch -q -c backup/snap main
commit "$repo" snap.txt snap-only
snap_sha="$(git -C "$repo" rev-parse backup/snap)"
git -C "$repo" switch -q -c feat/stacked
commit "$repo" stacked.txt stacked
git -C "$repo" switch -q main
git -C "$repo" worktree add -q "${work}/stack-feat" feat/stacked
commit "$repo" extra.txt extra
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --no-pr --no-prune >"${work}/stack.out" 2>&1 || fail "done must restack onto origin/main: $(cat "${work}/stack.out")"
git -C "$repo" merge-base --is-ancestor origin/main feat/stacked || fail "feat/stacked must be restacked onto origin/main"
[[ "$(git -C "$repo" rev-parse feat/stacked^)" != "$(git -C "$repo" rev-parse backup/snap)" ]] ||
	fail "feat/stacked must not have backup/snap as first parent"
git -C "$repo" show-ref --verify --quiet refs/heads/backup/snap || fail "backup/snap must still exist locally"
[[ "$(git -C "$repo" rev-parse backup/snap)" == "${snap_sha}" ]] || fail "backup/snap must stay at its original tip"
called_wt_sync_all && fail "wt-sync --all must not be called: $(cat "$WT_LOG")"

# --- One conflict does not stop others.
setup_clone split
git -C "$repo" switch -q -c feat/clash main
commit "$repo" clash.txt v1
git -C "$repo" push --no-verify -q origin feat/clash
git -C "$repo" reset --hard -q main
commit "$repo" clash.txt v2
clash_before="$(git -C "$repo" rev-parse feat/clash)"
git -C "$repo" switch -q -c feat/clean main
git -C "$repo" push --no-verify -q origin feat/clean
commit "$repo" clean.txt yes
clean_tip="$(git -C "$repo" rev-parse feat/clean)"
git -C "$repo" switch -q main
run_done "$repo" --no-pr --no-prune >"${work}/split.out" 2>&1 || fail "a single conflict must not fail done: $(cat "${work}/split.out")"
[[ "$(git -C "$origin" rev-parse feat/clean)" == "${clean_tip}" ]] || fail "the clean branch must reach origin"
[[ "$(git -C "$repo" rev-parse feat/clash)" == "${clash_before}" ]] || fail "the diverged local tip must stay unchanged"
[[ "$(git -C "$origin" rev-parse "backup/conflicts/split/feat/clash")" == "${clash_before}" ]] ||
	fail "the diverged tip must be copied to backup/conflicts/<clone>/<branch>"
called_wt_sync_all && fail "wt-sync --all must not be called: $(cat "$WT_LOG")"

# --- No worktree: restack must not switch the primary clone off main.
setup_clone stay
git -C "$repo" switch -q -c feat/loose
commit "$repo" loose.txt loose
loose_tip="$(git -C "$repo" rev-parse feat/loose)"
git -C "$repo" switch -q main
commit "$repo" extra.txt extra
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --no-pr --no-prune >"${work}/stay.out" 2>&1 || fail "done must push a branch with no worktree: $(cat "${work}/stay.out")"
[[ "$(git -C "$repo" symbolic-ref --short HEAD)" == main ]] ||
	fail "done must leave the primary clone on main, not $(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null || git -C "$repo" rev-parse --short HEAD)"
[[ "$(git -C "$origin" rev-parse feat/loose)" == "${loose_tip}" ]] || fail "a branch with no worktree must still be pushed as-is"

# --- Conflict backup matching the branch tip must not fail done.
setup_clone same
git -C "$repo" switch -q -c feat/same
commit "$repo" extra.txt from-feat
git -C "$repo" push --no-verify -q origin feat/same
git -C "$repo" switch -q main
git -C "$repo" worktree add -q "${work}/same-feat" feat/same
commit "$repo" extra.txt from-main
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --no-prune >"${work}/same.out" 2>&1 || fail "a same-commit conflict PR must not fail done: $(cat "${work}/same.out")"
grep -q 'pr create' "$WT_LOG" && fail "open_pr must not create a PR with no commits: $(cat "$WT_LOG")"

# --- --dry-run still only fetches.
setup_clone dry
git -C "$repo" switch -q -c feat/dry
commit "$repo" dry.txt a
printf 'b\n' >"${repo}/dry.txt"
dirty_before="$(git -C "$repo" status --porcelain)"
run_done "$repo" --dry-run --no-pr --no-prune >"${work}/dry.out" 2>&1 || fail "done --dry-run must succeed: $(cat "${work}/dry.out")"
[[ "$(git -C "$repo" status --porcelain)" == "${dirty_before}" ]] || fail "dry-run must leave the dirty file uncommitted"
grep -Eq 'would-restack +origin/main' "${work}/dry.out" || fail "dry-run must restack onto origin/main: $(cat "${work}/dry.out")"
grep -F 'wt-sync --all' "${work}/dry.out" && fail "dry-run must not restack with wt-sync --all: $(cat "${work}/dry.out")"
grep -Fq 'dry-run: fetched origin; no other changes' "${work}/dry.out" || fail "dry-run must only fetch"

# The script itself must disable quality hooks; the fixture did not export HK=0.
grep -Fq 'export HK=0' "$done" || fail "dev-profile-done must export HK=0 so hk cannot block parking"
grep -Eq 'commit -q --no-verify' "$done" || fail "dev-profile-done commits must pass --no-verify"
grep -Eq 'push --quiet --no-verify' "$done" || fail "dev-profile-done pushes must pass --no-verify"

echo "done fixture ok"
