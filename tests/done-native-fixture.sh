#!/usr/bin/env bash
# Public aliases invoke the installed Worktrunk; only forge and Trash are substitutes.
set -euo pipefail
export DONE_DEPLOY_CONFIG=1
source "$(dirname "$0")/done-support.sh"
repo=${repo:-}
origin=${origin:-}
work=${work:?fixture workspace missing}
root=${root:?fixture source root missing}
setup_clone native
printf 'keep me\n' >"$repo/local.txt"
run_done 'done' --drop --no-pr --no-prune >"$work/native.out" 2>&1 || fail "explicit done --drop must retire through native wt: $(cat "$work/native.out")"
[[ ! -d "$repo" ]] || fail 'explicit retirement must trash the clone'
[[ "$(git -C "$origin" show wip:local.txt)" == 'keep me' ]] || fail 'dirty work must reach origin'
[[ -d "$TRASH_DIR/native" ]] || fail 'trash must retain the clone'

# --config is process-local in native wt. The existing shim carries it through nested aliases.
setup_clone explicit-config
printf 'explicit config\n' >"$repo/explicit.txt"
config=$WORKTRUNK_CONFIG_PATH
(cd "$repo" && unset WORKTRUNK_CONFIG_PATH && "$root/bin/wt" -y --config "$config" 'done' -- --drop --no-pr --no-prune) >"$work/explicit-config.out" 2>&1 || fail "--config inheritance: $(cat "$work/explicit-config.out")"
[[ ! -d "$repo" && "$(git -C "$origin" show wip:explicit.txt)" == 'explicit config' ]] || fail 'explicit --config not inherited'

setup_clone relative-config
cp "$WORKTRUNK_CONFIG_PATH" "$repo/lifecycle.toml"
# Keep the test-only config outside the preserved file set.
printf 'lifecycle.toml\n' >>"$repo/.git/info/exclude"
printf 'relative config\n' >"$repo/relative.txt"
(unset WORKTRUNK_CONFIG_PATH && "$root/bin/wt" --config=lifecycle.toml -C "$repo" -y retire --no-pr --no-prune) >"$work/relative-config.out" 2>&1 || fail "relative --config= with -C: $(cat "$work/relative-config.out")"
[[ ! -d "$repo" && "$(git -C "$origin" show wip:relative.txt)" == 'relative config' ]] || fail 'relative --config=-C contract'
[[ -f "$TRASH_DIR/relative-config/lifecycle.toml" ]] || fail 'primary ignored files must remain in Trash'
# An externally gutted checkout is not an intentional repository-wide deletion.
setup_clone gutted
git -C "$repo" worktree add -q -b gutted-topic "$work/gutted-topic"
rm "$work/gutted-topic/base.txt"
run_done 'done' --no-pr --no-prune >"$work/gutted.out" 2>&1 || fail "gutted checkout: $(cat "$work/gutted.out")"
[[ -f "$work/gutted-topic/base.txt" ]] || fail 'gutted checkout must be restored before dirty classification'
[[ "$(git -C "$work/gutted-topic" rev-parse HEAD)" == "$(git -C "$origin" rev-parse main)" ]] || fail 'gutted checkout published mass deletions'

# Explicitly staged repository-wide deletion remains intentional.
setup_clone staged-all
rm "$repo/base.txt"
git -C "$repo" add -u
run_done 'done' --no-pr --no-prune >"$work/staged-all.out" 2>&1 || fail "staged all deletion: $(cat "$work/staged-all.out")"
if git -C "$origin" cat-file -e wip:base.txt 2>/dev/null; then fail 'staged deletion must not be restored'; fi

# A partial unstaged deletion must not be mistaken for a lost checkout.
setup_clone partial-delete
git -C "$repo" switch -q -c fixture-preparation
commit_file "$repo" remaining.txt remaining
git -C "$repo" switch -q main
git -C "$repo" merge --ff-only -q fixture-preparation
git -C "$origin" fetch -q "$repo" main:main
rm "$repo/base.txt"
run_done 'done' --no-pr --no-prune >"$work/partial-delete.out" 2>&1 || fail "partial deletion: $(cat "$work/partial-delete.out")"
[[ "$(git -C "$origin" show wip:remaining.txt)" == remaining ]] || fail 'partial deletion lost surviving file'
if git -C "$origin" cat-file -e wip:base.txt 2>/dev/null; then fail 'partial deletion must not be restored'; fi
echo 'done native fixture ok (explicit drop, native nested config, -C relative config, ignored primary Trash)'
