#!/usr/bin/env bash
# Every worktree gets its own host, whatever its branch: portless's own prefix
# would give feat/x and fix/x the same host (x), and none at all to a detached
# HEAD or a master branch. The script names the host itself, so all of these
# stay apart from each other and from the main checkout.
# Usage: routes.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
pair_repo "${repo}"
cd "${repo}"

expect_worktree_route() { # <dir> <branch args...> -- <expected route>
	local dir="$1" route="${*: -1}" args=("${@:2:$#-2}")
	git worktree add -q "${args[@]}" "${dir}"
	cd "${dir}"
	run_dev || fail "dev in worktree ${dir} must work"
	expect "^state=running url=https://${route//./\\.}\\.localhost pid=[0-9]+"
	[[ "$(sed -n 3p "${cache}/$(basename "${dir}").pid")" == "${route}" ]] ||
		fail "worktree ${dir} must record ${route} as its route"
	cd "${repo}"
}
expect_worktree_route "${work}/${rn}-feat-x" -B feat/x "feat-x.${rn}"
expect_worktree_route "${work}/${rn}-fix-x" -B fix/x "fix-x.${rn}"
expect_worktree_route "${work}/${rn}-detached" --detach "detached.${rn}"
expect_worktree_route "${work}/${rn}-master" -B master "master.${rn}"
# Four stacks at once on four different hosts.
hosts() { cut -f1 "${DEV_FIXTURE_SPAWNS}" | sort -u | grep -cE "^(feat-x|fix-x|detached|master)\\.${rn}\$" || :; }
four_hosts() { [[ "$(hosts)" == 4 ]]; }
wait_for four_hosts || :
[[ "$(hosts)" == 4 ]] ||
	fail "each worktree must register its own host"
for name in "${rn}-feat-x" "${rn}-fix-x" "${rn}-detached" "${rn}-master"; do
	stop_stack "${name}"
	git worktree remove --force "${work}/${name}"
done
git worktree prune

echo "dev-family routes fixture ok"
