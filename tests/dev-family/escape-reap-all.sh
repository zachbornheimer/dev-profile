#!/usr/bin/env bash
# A stack child that leaves the group outlives the tether, and a bare `reap`
# stops it: with nothing to name it stops the stack of every checkout that is
# gone and drops that stack's pidfile.
# Usage: escape-reap-all.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn='' escapee=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
git init -q -b main "${repo}"
git -C "${repo}" commit -q --allow-empty -m init
cd "${repo}"

esc="${work}/${rn}-esc2"
start_escaping "${repo}" "${esc}"
remove_escaping "${repo}" "${esc}"
run_dev reap || fail "reap must succeed with nothing to name"
wait_for gone "${escapee}" || fail "reap must stop the stack of every checkout that is gone"
[[ ! -e "${cache}/${rn}-esc2.pid" ]] || fail "reap must drop the pidfile of a checkout that is gone"

echo "dev-family escape-reap-all fixture ok"
