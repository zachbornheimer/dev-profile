#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/worktree-start.sh: `mise run generate` copies it into bin/.

# Worktrunk's only post-start entry, so its two halves cannot race: worktrunk
# runs post-start entries concurrently, and a dev stack that starts before the
# copy has landed serves a vendor/ that points at another checkout (PHP dies on
# the app's own classes, and the half-up stack then holds the route).
#
# Start through `mise run dev`, never a dispatcher binary: the code root's own
# profile decides which implementation `dev` is (personal and SAH differ), so
# this hook names none and there is one dispatcher per route.
usage="usage: dev-profile-worktree-start [--help]"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
	echo "${usage}"
	exit 0
fi
[[ $# -eq 0 ]] || {
	echo "${usage}" >&2
	exit 2
}

root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
	echo "dev-profile-worktree-start: ${PWD} is not inside a git repository" >&2
	exit 2
}
cd "${root}"

# The copy half, with its own failure: a start without the copied files is
# wrong. Repeated once per checkout only, so re-entering a worktree neither
# reflinks the tree again nor re-dumps the autoloader. The marker sits in this
# checkout's git dir, so it leaves with the worktree.
marker="$(git rev-parse --git-dir)/.worktree-copied"
if [[ ! -e "${marker}" ]]; then
	here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
	"${here}/dev-profile-worktree-copy"
	: >"${marker}"
fi

# Marker-only repos outside either code root need no dev task installed.
if [[ ! -x mise-tasks/dev-serve && ! -f composer.json ]]; then
	if [[ ! -f package.json ]] || ! jq -e '.scripts.dev // empty' package.json >/dev/null; then
		exit 0
	fi
fi
exec mise run dev
