#!/usr/bin/env bash
# Public sync uses native operations; forge/Trash and host hooks use done-support's sandbox.
set -euo pipefail
export DONE_DEPLOY_CONFIG=1
source "$(dirname "$0")/done-support.sh"
repo=${repo:-}
origin=${origin:-}
work=${work:?fixture workspace missing}
root=${root:?fixture source root missing}
setup_clone sync
# A plugin that happens to remain installed must never receive the invocation.
preview=$(run_done config alias dry-run sync -- --push-only)
[[ "$preview" != *wt-sync* ]] || fail 'public sync still invokes legacy plugin'
printf '#!/bin/sh\necho "legacy sync invoked" >&2\nexit 92\n' >"$work/tools/wt-sync"
chmod +x "$work/tools/wt-sync"
git -C "$repo" switch -q -c feature
commit_file "$repo" feature.txt feature
run_done sync -- --push-only >"$work/unpublished-sync.out" 2>&1 || fail "sync without upstream: $(cat "$work/unpublished-sync.out")"
[[ -z "$(git -C "$origin" for-each-ref refs/heads/feature)" ]] || fail 'sync must not invent an upstream'
git -C "$origin" fetch -q "$repo" feature:feature
git -C "$repo" fetch -q origin
git -C "$repo" branch --set-upstream-to=origin/feature feature >/dev/null
git -C "$repo" switch -q -c advance main
commit_file "$repo" advanced.txt advanced
git -C "$origin" fetch -q "$repo" advance:main
git -C "$repo" switch -q feature
refs_before=$(git -C "$repo" show-ref)
fetch_before=$(git -C "$repo" hash-object .git/FETCH_HEAD)
run_done sync -- -u -p --dry-run >"$work/sync-dry.out" 2>&1 || fail "sync dry-run: $(cat "$work/sync-dry.out")"
[[ "$(git -C "$repo" show-ref)" == "$refs_before" && "$(git -C "$repo" hash-object .git/FETCH_HEAD)" == "$fetch_before" ]] || fail 'sync dry-run must not fetch, rebase or push'
run_done sync -- -u -p >"$work/sync.out" 2>&1 || fail "native sync: $(cat "$work/sync.out")"
git -C "$repo" merge-base --is-ancestor origin/main feature || fail 'sync did not rebase onto origin/main'
[[ "$(git -C "$origin" rev-parse feature)" == "$(git -C "$repo" rev-parse feature)" ]] || fail 'sync did not publish rebased upstream'
git -C "$repo" verify-commit feature >/dev/null 2>&1 || fail 'native rebase must retain configured signing'
commit_file "$repo" another.txt another
run_done sync -- --push-only >"$work/push-only.out" 2>&1 || fail "push-only: $(cat "$work/push-only.out")"
[[ "$(git -C "$origin" rev-parse feature)" == "$(git -C "$repo" rev-parse feature)" ]] || fail 'push-only did not publish upstream'
mkdir -p "$repo/.git/hooks"
printf '#!/bin/sh\nexit 1\n' >"$repo/.git/hooks/pre-push"
chmod +x "$repo/.git/hooks/pre-push"
commit_file "$repo" refused.txt refused
remote_before=$(git -C "$origin" rev-parse feature)
if run_done sync -- --push-only >"$work/sync-refused.out" 2>&1; then fail 'sync must propagate push hook failure'; fi
[[ "$(git -C "$origin" rev-parse feature)" == "$remote_before" ]] || fail 'sync bypassed pre-push hook'
rm "$repo/.git/hooks/pre-push"
for option in --stack --force --not-a-sync-option; do
	if run_done sync -- "$option" >"$work/sync-invalid.out" 2>&1; then fail "sync accepted unsupported $option"; fi
done
# Branch binding selects an existing worktree, not a different interpretation of HEAD.
git -C "$repo" worktree add -q -b linked-sync "$work/linked-sync" main
commit_file "$work/linked-sync" linked.txt linked
git -C "$origin" fetch -q "$work/linked-sync" linked-sync:linked-sync
git -C "$repo" fetch -q origin
git -C "$repo" branch --set-upstream-to=origin/linked-sync linked-sync >/dev/null
commit_file "$work/linked-sync" linked-more.txt more
run_done sync --branch=linked-sync -- --push-only >"$work/sync-branch.out" 2>&1 || fail "sync branch binding: $(cat "$work/sync-branch.out")"
[[ "$(git -C "$origin" rev-parse linked-sync)" == "$(git -C "$repo" rev-parse linked-sync)" ]] || fail 'branch binding pushed wrong worktree'
run_done sync -- --all --push-only >"$work/sync-all.out" 2>&1 || fail "sync all: $(cat "$work/sync-all.out")"
[[ "$(git -C "$origin" rev-parse feature)" == "$(git -C "$repo" rev-parse feature)" ]] || fail 'all did not publish invoking branch'
# Exercise real switch/argument routing; the forge adapter is the narrow substitute.
mkdir -p "$work/home/.local/share/dev-profile/bin"
export PR_ALIAS_LOG="$work/pr-alias.log"
cat >"$work/home/.local/share/dev-profile/bin/dev-profile-pr" <<'PR'
#!/usr/bin/env bash
printf '%s\n' "$PWD" "$@" >"$PR_ALIAS_LOG"
PR
chmod +x "$work/home/.local/share/dev-profile/bin/dev-profile-pr"
for mode in pr pr-draft pr-auto; do
	HOME="$work/home" run_done "$mode" feature >"$work/$mode.out" 2>&1 || fail "$mode routing: $(cat "$work/$mode.out")"
	[[ "$(head -1 "$PR_ALIAS_LOG")" == "$repo" ]] || fail "$mode selected wrong worktree"
	case "$mode" in
	pr) [[ "$(wc -l <"$PR_ALIAS_LOG")" -eq 1 ]] || fail 'plain pr invented adapter flags' ;;
	pr-draft) grep -Fxq -- --draft "$PR_ALIAS_LOG" || fail 'draft flag lost' ;;
	pr-auto) grep -Fxq -- --auto "$PR_ALIAS_LOG" || fail 'auto flag lost' ;;
	esac
	HOME="$work/home" run_done "$mode" --create="new-$mode" -- printf '%s' 'two words' >"$work/create-$mode.out" 2>&1 || fail "$mode create: $(cat "$work/create-$mode.out")"
	grep -Fxq -- 'two words' "$PR_ALIAS_LOG" || fail "$mode split post-create argument"
	grep -Fxq -- -- "$PR_ALIAS_LOG" || fail "$mode lost post-create command separator"
done
echo 'native alias fixture ok (sync dry-run, rebase, signing, upstream, push hooks, branch binding, all, unsupported options)'
