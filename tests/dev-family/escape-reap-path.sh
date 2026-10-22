#!/usr/bin/env bash
# A stack child that leaves the group outlives the tether, and `reap <path>`
# stops it: it refuses a live checkout, and for a removed worktree stops the
# escaped child and drops the stack's pidfile.
# Usage: escape-reap-path.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn='' escapee=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
git init -q -b main "${repo}"
git -C "${repo}" commit -q --allow-empty -m init
cd "${repo}"

esc="${work}/${rn}-esc1"
start_escaping "${repo}" "${esc}"
remove_escaping "${repo}" "${esc}"
if run_dev reap "${repo}"; then fail "reap <path> must refuse a live checkout"; fi
expect 'is a live checkout'
run_dev reap "${esc}" || fail "reap <path> must succeed for a removed worktree"
wait_for gone "${escapee}" || fail "reap <path> must stop the child that left the group"
[[ ! -e "${cache}/${rn}-esc1.pid" ]] || fail "reap <path> must drop the stack's pidfile"

echo "dev-family escape-reap-path fixture ok"
