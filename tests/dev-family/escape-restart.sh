#!/usr/bin/env bash
# A stack child that leaves the group outlives the tether, and dev:restart stops
# it: the restart of a live worktree's stack takes the escaped child with it.
# Usage: escape-restart.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' rn='' escapee=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
git init -q -b main "${repo}"
git -C "${repo}" commit -q --allow-empty -m init
cd "${repo}"

esc="${work}/${rn}-esc3"
start_escaping "${repo}" "${esc}"
old="${escapee}"
cd "${esc}"
run_dev restart || fail "dev:restart must work for a stack with an escaping child"
cd "${repo}"
wait_for gone "${old}" || fail "dev:restart must stop the child that left the group"
stop_stack "${rn}-esc3"
git worktree remove --force "${esc}"
git worktree prune

echo "dev-family escape-restart fixture ok"
