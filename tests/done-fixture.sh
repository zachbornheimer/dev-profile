#!/usr/bin/env bash
# Behavior at the real native wt CLI boundary, with signed Git commits/hooks.
set -euo pipefail
source "$(dirname "$0")/done-support.sh"

setup_clone keep
printf 'dirty\n' >"$repo/base.txt"
printf 'untracked\n' >"$repo/new file.txt"
run_done done --no-pr --no-prune >"$work/keep.out" 2>&1 || fail "plain done: $(cat "$work/keep.out")"
[[ -d "$repo" ]] || fail 'plain done must retain clone'
[[ "$(git -C "$origin" show wip:base.txt)" == dirty ]] || fail 'tracked edit not published'
[[ "$(git -C "$origin" show 'wip:new file.txt')" == untracked ]] || fail 'untracked file not published'
[[ "$(git -C "$repo" branch --show-current)" == main ]] || fail 'primary must stay on main'
git -C "$origin" cat-file -p wip | grep -q '^gpgsig' || fail 'snapshot must keep authoritative signing'
git -C "$repo" verify-commit wip >/dev/null 2>&1 || fail 'snapshot signature must verify'

setup_clone hooks
printf 'retained\n' >"$repo/local.txt"
mkdir -p "$repo/.git/hooks"
cat >"$repo/.git/hooks/pre-commit" <<'HOOK'
#!/usr/bin/env sh
exit 1
HOOK
chmod +x "$repo/.git/hooks/pre-commit"
# A repository hook supplements global scanner hooks; it does not disable them.
if run_done retire --no-pr >"$work/hooks.out" 2>&1; then fail 'failed commit hook must stop retirement'; fi
[[ -d "$repo" && "$(cat "$repo/local.txt")" == retained ]] || fail 'failed hook must retain dirty file'

setup_clone pushhook
git -C "$repo" switch -q -c feature
commit_file "$repo" tip.txt original
tip=$(git -C "$repo" rev-parse HEAD)
mkdir -p "$repo/.git/hooks"
printf '#!/bin/sh\nexit 1\n' >"$repo/.git/hooks/pre-push"
chmod +x "$repo/.git/hooks/pre-push"
if run_done drop --no-pr >"$work/pushhook.out" 2>&1; then fail 'failed push hook must stop drop'; fi
[[ -d "$repo" ]] || fail 'failed push hook lost clone'
[[ "$(git -C "$repo" rev-parse feature)" == "$tip" ]] || fail 'failed push hook lost branch'
[[ -z "$(git -C "$origin" for-each-ref refs/heads/feature)" ]] || fail 'push hook was bypassed'

setup_clone remote-reject
git -C "$repo" switch -q -c feature
commit_file "$repo" retained.txt retained
printf '#!/bin/sh\nexit 1\n' >"$origin/hooks/pre-receive"
chmod +x "$origin/hooks/pre-receive"
if run_done retire --no-pr >"$work/remote-reject.out" 2>&1; then fail 'rejected push must stop retirement'; fi
[[ -f "$repo/retained.txt" ]] || fail 'remote rejection lost work'

setup_clone detached
git -C "$repo" switch -q --detach
commit_file "$repo" detached.txt detached
detached=$(git -C "$repo" rev-parse HEAD)
run_done done --no-pr --no-prune >"$work/detached.out" 2>&1 || fail "detached HEAD: $(cat "$work/detached.out")"
[[ -n "$(git -C "$origin" for-each-ref --contains "$detached" refs/heads)" ]] || fail 'detached tip not published'

setup_clone stashclash
printf 'stashed\n' >"$repo/base.txt"
printf 'stash-untracked\n' >"$repo/stash-only.txt"
git -C "$repo" stash push -u -q
git -C "$repo" switch -q -c advance
commit_file "$repo" base.txt advanced
git -C "$repo" switch -q main
git -C "$repo" merge --ff-only -q advance
git -C "$origin" fetch -q "$repo" main:main
git -C "$repo" branch wip/topic
run_done retire --no-pr >"$work/stash.out" 2>&1 || fail "conflicting stash: $(cat "$work/stash.out")"
[[ ! -d "$repo" ]] || fail 'retire did not trash stash clone'
[[ "$(git -C "$origin" show wip-2:base.txt)" == stashed ]] || fail 'conflicting stash snapshot lost'
[[ "$(git -C "$origin" show wip-2:stash-only.txt)" == stash-untracked ]] || fail 'stash untracked file lost'
git -C "$origin" cat-file -p wip-2 | grep -q '^gpgsig' || fail 'stash snapshot unsigned'
git -C "$TRASH_DIR/stashclash" verify-commit wip-2 >/dev/null 2>&1 || fail 'stash snapshot signature must verify'

setup_clone conflict
git -C "$repo" switch -q -c feature
commit_file "$repo" base.txt remote-version
git -C "$origin" fetch -q "$repo" feature:feature
git -C "$repo" reset --hard -q main
commit_file "$repo" base.txt local-version
local_tip=$(git -C "$repo" rev-parse feature)
run_done done --no-pr --no-prune >"$work/conflict.out" 2>&1 || fail "diverged branch: $(cat "$work/conflict.out")"
[[ "$(git -C "$origin" show feature:base.txt)" == remote-version ]] || fail 'remote overwritten'
[[ "$(git -C "$origin" rev-parse backup/conflicts/conflict/feature)" == "$local_tip" ]] || fail 'conflict backup missing'
commit_file "$repo" extra.txt later
run_done done --no-pr --no-prune >"$work/conflict2.out" 2>&1 || fail "second diverged snapshot: $(cat "$work/conflict2.out")"
[[ "$(git -C "$origin" rev-parse backup/conflicts/conflict/feature)" == "$local_tip" ]] || fail 'prior conflict backup overwritten'

setup_clone linked
git -C "$repo" worktree add -q -b topic "$work/linked-topic"
printf 'linked\n' >"$work/linked-topic/linked.txt"
git -C "$repo" worktree lock "$work/linked-topic"
run_done done --no-pr >"$work/linked-keep.out" 2>&1 || fail "locked worktree: $(cat "$work/linked-keep.out")"
[[ -d "$work/linked-topic" ]] || fail 'plain done removed locked worktree'
run_done drop --no-pr >"$work/linked-drop.out" 2>&1 || fail "explicit locked drop: $(cat "$work/linked-drop.out")"
[[ ! -d "$repo" && ! -d "$work/linked-topic" ]] || fail 'explicit drop must remove linked worktree and trash primary'
[[ "$(git -C "$origin" show topic:linked.txt)" == linked ]] || fail 'linked work not preserved'

setup_clone size
head -c 1048577 /dev/zero >"$repo/large.bin"
if DEV_PROFILE_SYNC_MAX_FILE_MB=1 run_done retire --no-pr >"$work/size.out" 2>&1; then fail 'size gate must stop retirement'; fi
[[ -f "$repo/large.bin" ]] || fail 'size refusal lost file'

setup_clone nested
git init -q "$repo/child"
if run_done drop --no-pr >"$work/nested.out" 2>&1; then fail 'nested repo must stop retirement'; fi
[[ -d "$repo/child/.git" ]] || fail 'nested refusal lost repository'

setup_clone dry
printf 'unchanged\n' >"$repo/dry.txt"
before=$(git -C "$repo" status --porcelain)
run_done done -- --drop --dry-run >"$work/dry.out" 2>&1 || fail "dry run: $(cat "$work/dry.out")"
[[ -d "$repo" && "$(git -C "$repo" status --porcelain)" == "$before" ]] || fail 'dry run changed work'

setup_clone no-push
printf 'retained\n' >"$repo/local.txt"
if run_done retire --no-push --no-pr >"$work/no-push.out" 2>&1; then fail 'unpublished tips must stop retirement'; fi
[[ -d "$repo" ]] || fail '--no-push lost clone'

setup_clone staged
printf 'staged\n' >"$repo/staged.txt"
git -C "$repo" add staged.txt
rm "$repo/base.txt"
run_done done --no-pr --no-prune >"$work/staged.out" 2>&1 || fail "staged/deletion: $(cat "$work/staged.out")"
[[ "$(git -C "$origin" show wip:staged.txt)" == staged ]] || fail 'staged bytes missing'
if git -C "$origin" cat-file -e wip:base.txt 2>/dev/null; then fail 'intentional deletion resurrected'; fi

setup_clone branch-only
git -C "$repo" switch -q -c orphan-work
commit_file "$repo" branch.txt branch-only
branch_tip=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" switch -q main
run_done done --no-pr --no-prune >"$work/branch-only.out" 2>&1 || fail "branch-only: $(cat "$work/branch-only.out")"
[[ "$(git -C "$origin" rev-parse orphan-work)" == "$branch_tip" ]] || fail 'branch without worktree missing'

setup_clone secondary
secondary="$work/secondary-backup.git"
git init -q --bare "$secondary"
git -C "$repo" switch -q -c local-only
commit_file "$repo" secondary.txt secondary
secondary_tip=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" remote add backup "$secondary"
git -C "$secondary" fetch -q "$repo" local-only:local-only
git -C "$repo" fetch -q backup
if run_done retire --no-push --no-pr >"$work/secondary.out" 2>&1; then fail 'secondary remote cannot authorize retirement'; fi
[[ -d "$repo" && "$(git -C "$repo" rev-parse local-only)" == "$secondary_tip" ]] || fail 'origin containment refusal lost branch'

setup_clone multi-stash
printf 'first\n' >"$repo/base.txt"
printf 'first-only\n' >"$repo/first.txt"
git -C "$repo" stash push -u -q
printf 'second\n' >"$repo/base.txt"
printf 'second-only\n' >"$repo/second.txt"
git -C "$repo" stash push -u -q
git -C "$origin" fetch -q "$repo" main:refs/heads/wip/remote
run_done done --no-pr --no-prune >"$work/multi-stash.out" 2>&1 || fail "multiple stashes: $(cat "$work/multi-stash.out")"
[[ "$(git -C "$origin" show wip-2:base.txt)" == second ]] || fail 'latest stash conflict bytes missing'
[[ "$(git -C "$origin" show wip-2:second.txt)" == second-only ]] || fail 'latest stash untracked missing'
[[ "$(git -C "$origin" show wip-3:base.txt)" == first ]] || fail 'older stash conflict bytes missing'
[[ "$(git -C "$origin" show wip-3:first.txt)" == first-only ]] || fail 'older stash untracked missing'
[[ -z "$(git -C "$repo" stash list)" ]] || fail 'published stashes were not cleared'

setup_clone ignored
git -C "$repo" worktree add -q -b ignored-topic "$work/ignored-topic"
printf 'private.bin\n' >"$repo/.git/info/exclude"
printf 'private bytes\n' >"$work/ignored-topic/private.bin"
run_done done --no-pr >"$work/ignored-keep.out" 2>&1 || fail "ignored keep: $(cat "$work/ignored-keep.out")"
[[ "$(cat "$work/ignored-topic/private.bin")" == 'private bytes' ]] || fail 'plain prune discarded ignored data'
if run_done retire --no-pr >"$work/ignored-drop.out" 2>&1; then fail 'retirement must reject unpreserved linked ignored data'; fi
[[ -d "$repo" && "$(cat "$work/ignored-topic/private.bin")" == 'private bytes' ]] || fail 'retirement lost linked ignored data'

setup_clone submodule
mkdir -p "$repo/.git/modules/absent"
if run_done retire --no-pr >"$work/submodule.out" 2>&1; then fail 'submodule object store must block retirement'; fi
[[ -d "$repo/.git/modules/absent" ]] || fail 'submodule metadata removed'

setup_clone aggregate
git -C "$repo" worktree add -q -b reject "$work/aggregate-reject"
printf 'reject\n' >"$work/aggregate-reject/secret.txt"
mkdir -p "$repo/.git/hooks"
printf '#!/bin/sh\ncase "$PWD" in *aggregate-reject) exit 1 ;; esac\n' >"$repo/.git/hooks/pre-commit"
chmod +x "$repo/.git/hooks/pre-commit"
if run_done drop --no-pr >"$work/aggregate.out" 2>&1; then fail 'for-each failure must stop before removal'; fi
[[ -d "$repo" && "$(cat "$work/aggregate-reject/secret.txt")" == reject ]] || fail 'aggregate failure removed worktree'

setup_clone late-write
git -C "$repo" worktree add -q -b late-topic "$work/late-topic"
commit_file "$work/late-topic" late.txt original
cat >>"$WORKTRUNK_CONFIG_PATH" <<'TOML'
[pre-remove]
late-write = 'printf "late bytes\n" > late-arrival.txt'
TOML
if run_done drop --no-pr >"$work/late-write.out" 2>&1; then fail 'pre-remove new work must stop removal'; fi
[[ -d "$repo" && "$(cat "$work/late-topic/late-arrival.txt")" == 'late bytes' ]] || fail 'late hook write lost'
# Restore the fixture config by removing only our appended test hook (Python fixture utility, not production hook bypass).
python3 - "$WORKTRUNK_CONFIG_PATH" <<'PY'
import sys
p=sys.argv[1]
s=open(p).read()
s=s[:s.rindex('[pre-remove]')]
open(p,'w').write(s)
PY

# Project hooks run after user hooks; the final native hook must guard both.
for operation in done drop; do
	setup_clone "ignored-hook-$operation"
	git -C "$repo" worktree add -q -b hook-topic "$work/ignored-hook-$operation-topic"
	printf 'hook-private.bin\n' >>"$repo/.git/info/exclude"
	mkdir -p "$work/ignored-hook-$operation-topic/.config"
	cat >"$work/ignored-hook-$operation-topic/.config/wt.toml" <<'TOML'
[pre-remove]
write-private = 'printf "hook private bytes\n" > hook-private.bin'
TOML
	git -C "$work/ignored-hook-$operation-topic" add .config/wt.toml
	git -C "$work/ignored-hook-$operation-topic" commit -q -m 'test: configure ignored hook writer'
	git -C "$repo" merge --ff-only -q hook-topic
	git -C "$origin" fetch -q "$repo" main:main
	# Clear only the fixture isolation override so the actual per-tree project config loads.
	if (
		unset WORKTRUNK_PROJECT_CONFIG_PATH
		run_done "$operation" --no-pr
	) >"$work/ignored-hook-$operation.out" 2>&1; then
		fail 'late ignored write must stop removal'
	fi
	[[ -d "$repo" && "$(cat "$work/ignored-hook-$operation-topic/hook-private.bin")" == 'hook private bytes' ]] || fail 'late ignored project hook lost bytes'
done

setup_clone missing
git -C "$repo" worktree add -q -b missing-topic "$work/missing-topic"
printf 'staged recovery\n' >"$work/missing-topic/staged.txt"
git -C "$work/missing-topic" add staged.txt
mv "$work/missing-topic" "$work/missing-recovery"
if run_done retire --no-pr >"$work/missing.out" 2>&1; then fail 'missing worktree must stop retirement before pruning metadata'; fi
[[ -d "$repo/.git/worktrees/missing-topic" && "$(cat "$work/missing-recovery/staged.txt")" == 'staged recovery' ]] || fail 'missing worktree recovery state lost'

setup_clone restack
git -C "$repo" switch -q -c feature
commit_file "$repo" feature.txt feature
original=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" switch -q -c upstream-advance main
commit_file "$repo" advanced.txt advanced
git -C "$origin" fetch -q "$repo" upstream-advance:main
git -C "$repo" switch -q feature
run_done done --no-pr --no-prune >"$work/restack.out" 2>&1 || fail "restack: $(cat "$work/restack.out")"
[[ "$(git -C "$origin" rev-parse "backup/restack/$original")" == "$original" ]] || fail 'original restack tip not preserved'
git -C "$repo" merge-base --is-ancestor origin/main feature || fail 'feature not restacked'

# Informational forms must leave repository bytes and refs untouched.
setup_clone information
printf 'informational\n' >"$repo/info.txt"
git -C "$repo" add info.txt
refs_before=$(git -C "$repo" show-ref)
index_before=$(git -C "$repo" hash-object .git/index)
fetch_before=$(git -C "$repo" hash-object .git/FETCH_HEAD)
fetch_mtime=$(python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$repo/.git/FETCH_HEAD")
status_before=$(git -C "$repo" --no-optional-locks status --porcelain)
stash_before=$(git -C "$repo" stash list --format=%H)
for command in done retire drop; do
	run_done "$command" --help >"$work/$command-help.out" 2>&1 || fail "$command help"
	run_done "$command" -- --dry-run >"$work/$command-dry.out" 2>&1 || fail "$command dry-run"
done
[[ "$(git -C "$repo" show-ref)" == "$refs_before" ]] || fail 'informational command changed refs'
[[ "$(git -C "$repo" hash-object .git/index)" == "$index_before" ]] || fail 'informational command changed index'
[[ "$(git -C "$repo" hash-object .git/FETCH_HEAD)" == "$fetch_before" && "$(python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$repo/.git/FETCH_HEAD")" == "$fetch_mtime" ]] || fail 'informational command fetched'
[[ "$(git -C "$repo" --no-optional-locks status --porcelain)" == "$status_before" && "$(git -C "$repo" stash list --format=%H)" == "$stash_before" ]] || fail 'informational command changed status or stashes'
[[ "$(cat "$repo/info.txt")" == informational ]] || fail 'informational command changed bytes'
echo 'done fixture ok (keep, hooks, remote rejection, detached, stashes, conflicts, locked worktrees, size, nested, dry-run, unpublished)'
