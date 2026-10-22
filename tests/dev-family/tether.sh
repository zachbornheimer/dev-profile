#!/usr/bin/env bash
# A linked worktree claims <branch>.<repo>.localhost, under worktrunk's tether:
# the recorded pid is the stack's process-group leader, restart goes through the
# same spawn path and replaces the group, and removing the worktree reaps the
# restarted tree. Usage: tether.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
pair_repo "${repo}"
cd "${repo}"

wt="${work}/${rn}-feat-x"
git worktree add -q -b feat/x "${wt}"
cd "${wt}"
run_dev || fail "dev in a worktree must work"
expect "^state=running url=https://feat-x\\.${rn}\\.localhost pid=[0-9]+\$"
expect_spawn_name "feat-x.${rn}"
[[ "$(sed -n 3p "${cache}/${rn}-feat-x.pid")" == "feat-x.${rn}" ]] ||
	fail "a branch worktree must record <branch>.<repo> as its route"
leader="$(sed -n 1p "${cache}/${rn}-feat-x.pid")"
group "${leader}" || fail "the tether must record a stack's process-group leader"

# restart goes through the same spawn path: a fresh group, still one leader, and
# the group it replaced is gone.
old="${leader}"
# Whatever the stubs record from here on belongs to the restarted tree, or to the
# group it replaced, which is already gone.
floor="$(lines "${DEV_FIXTURE_PIDS}")"
run_dev restart || fail "dev:restart in a worktree must work"
leader="$(sed -n 1p "${cache}/${rn}-feat-x.pid")"
[[ "${leader}" != "${old}" ]] || fail "dev:restart must start a new stack"
group "${leader}" || fail "dev:restart must tether the new stack too"
if kill -0 "${old}" 2>/dev/null; then fail "dev:restart must stop the old group"; fi

# Removing the worktree reaps the restarted tree, not just the first one. The
# tether's watcher polls, so allow a generous window before judging it.
cd "${repo}"
sleep 1
git worktree remove --force "${wt}"
git worktree prune
waited=0
while [[ -n "$(survivors "${floor}")" && "${waited}" -lt 20 ]]; do
	sleep 1
	waited=$((waited + 1))
done
[[ -z "$(survivors "${floor}")" ]] ||
	fail "removing the worktree must reap the tethered stack; survivors: $(survivors "${floor}")"

echo "dev-family tether fixture ok"
