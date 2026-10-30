#!/usr/bin/env bash
set -euo pipefail
# Edit lib/pr-watch.sh: `mise run generate` copies it into bin/.

# Watch a PR through CI, merge it when green, notify, then remove its branch
# and worktree. Started by `wt pr-auto`; safe to run by hand.
#   DEV_PROFILE_PR_POLL          seconds between GitHub polls (default 15)
#   DEV_PROFILE_PR_CHECKS_WAIT   seconds to wait for CI to report checks (default 120)
#   DEV_PROFILE_PR_MERGE_WAIT    seconds to wait for GitHub to merge (default 14400)
#   DEV_PROFILE_PR_MERGE_METHOD  merge|squash|rebase (default: your repo default)
pr="${1:?usage: dev-profile-pr-watch <pr-url-or-number>}"
# An unexpected error must never vanish with its tab. Until the PR is known,
# say where it stopped (and stay open in a terminal); fail() takes over below.
set -E
trap 'echo "dev-profile-pr-watch stopped at line ${LINENO}: ${BASH_COMMAND}" >&2; if [[ -t 0 && -t 1 ]]; then exec "${SHELL:-/bin/zsh}" -i; fi' ERR
poll="${DEV_PROFILE_PR_POLL:-15}"
checks_wait="${DEV_PROFILE_PR_CHECKS_WAIT:-120}"
merge_wait="${DEV_PROFILE_PR_MERGE_WAIT:-14400}"

# shellcheck source=lib/sh/gh-scope.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/gh-scope.sh"

info="$(ghr pr view "${pr}" --json number,title,url,headRefName,isCrossRepository)"
number="$(jq -r .number <<<"${info}")"
title="$(jq -r .title <<<"${info}")"
url="$(jq -r .url <<<"${info}")"
branch="$(jq -r .headRefName <<<"${info}")"
from_fork="$(jq -r .isCrossRepository <<<"${info}")"

in_kitty() { [[ -t 1 && "${TERM:-}" == xterm-kitty ]] && command -v kitten >/dev/null; }

# The tab title tracks progress; the log line keeps a timeline.
status() {
	if in_kitty; then printf '\033]2;PR #%s: %s\007' "${number}" "$1"; fi
	echo "$(date +%H:%M:%S) PR #${number}: $1"
}

# notify <normal|critical> <title> <body>: desktop notification. In kitty,
# clicking it focuses this tab.
notify() {
	if in_kitty; then
		kitten notify --app-name "wt pr" --identifier "wt-pr-${number}" --urgency "$1" "$2" "$3"
	elif command -v terminal-notifier >/dev/null; then
		terminal-notifier -title "$2" -message "$3" -open "${url}" -group "wt-pr-${number}" >/dev/null
	elif command -v osascript >/dev/null; then
		osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' \
			-e 'end run' "$2" "$3"
	fi || true
}

# mark_tab <color> <outcome>: colour the tab and pin its title, so the outcome
# stays visible after a shell takes the window over.
mark_tab() {
	[[ -n "${KITTY_LISTEN_ON:-}" && -n "${KITTY_WINDOW_ID:-}" ]] || return 0
	local tab=(--to "${KITTY_LISTEN_ON}")
	kitten @ "${tab[@]}" set-tab-color --match "window_id:${KITTY_WINDOW_ID}" \
		"active_bg=$1" "inactive_bg=$1" >/dev/null 2>&1 || true
	kitten @ "${tab[@]}" set-tab-title --match "window_id:${KITTY_WINDOW_ID}" \
		"PR #${number}: $2" >/dev/null 2>&1 || true
}

# Report a failure; in a terminal, stay open in a shell to fix it.
fail() {
	status "$1"
	mark_tab "#b03030" "$1"
	notify critical "PR #${number}: $1" "${title}"
	echo "${url}"
	if [[ -t 0 && -t 1 ]]; then
		echo "Fix, then rerun: wt pr-auto. Exit this shell to close the tab."
		exec "${SHELL:-/bin/zsh}" -i
	fi
	exit 1
}
trap 'trap - ERR; fail "stopped unexpectedly at line ${LINENO}: ${BASH_COMMAND}"' ERR

# gh exits 1 on a PR without checks. `|| true` sits inside the substitution:
# set -E fires the ERR trap in the subshell, and fail() would print into n.
check_count() {
	local n
	n="$(ghr pr checks "${pr}" --json name --jq length 2>/dev/null || true)"
	[[ "${n}" =~ ^[0-9]+$ ]] || n=0
	echo "${n}"
}
no_checks() { [[ "$(ghr pr checks "${pr}" 2>&1 >/dev/null || true)" == *"no checks reported"* ]]; }

# OPEN, MERGED or CLOSED; UNKNOWN when GitHub cannot be reached, so a network
# blip keeps polling instead of reading as closed.
pr_state() { ghr pr view "${pr}" --json state --jq .state 2>/dev/null || echo UNKNOWN; }
settled() { [[ "$1" == MERGED || "$1" == CLOSED ]]; }

# Wait for CI to report checks, then for them to pass.
await_ci() {
	status "waiting for CI to start"
	local deadline=$((SECONDS + checks_wait))
	while [[ "$(check_count)" -eq 0 && "${SECONDS}" -lt "${deadline}" ]]; do sleep "${poll}"; done
	if [[ "$(check_count)" -eq 0 ]]; then
		status "no CI checks reported"
		return 0
	fi
	# Workflows register one by one: a fast first check must not let the
	# watch pass before slower ones appear. Wait for the count to hold.
	local seen=0 now
	while now="$(check_count)" && [[ "${now}" -ne "${seen}" ]]; do
		seen="${now}"
		sleep "${poll}"
	done
	status "CI running"
	if ! ghr pr checks "${pr}" --watch --fail-fast --interval "$((poll > 0 ? poll : 1))"; then
		no_checks || fail "CI failed"
		status "no CI checks reported"
	fi
}

# gh merges at once when GitHub allows it; otherwise auto-merge waits for
# reviews or required checks, so poll until GitHub reports the outcome.
merge() {
	local method="${DEV_PROFILE_PR_MERGE_METHOD:-$(gh repo view ${slug:+"${slug}"} --json viewerDefaultMergeMethod \
		--jq '.viewerDefaultMergeMethod | ascii_downcase')}"
	status "merging (${method})"
	local refusal
	if ! refusal="$(ghr pr merge "${pr}" --auto "--${method}" 2>&1)"; then
		# Private repos on the Free plan refuse auto-merge outright. Checks are
		# already green (or absent) here, the condition auto-merge would wait for.
		if [[ "${refusal}" == *"Auto merge is not allowed"* ]]; then
			status "auto-merge not allowed here; merging directly"
			ghr pr merge "${pr}" "--${method}" --delete-branch=false || fail "merge refused"
		else
			echo "${refusal}" >&2
			fail "merge refused"
		fi
	fi
	local deadline=$((SECONDS + merge_wait))
	while state="$(pr_state)" && ! settled "${state}"; do
		if [[ "${SECONDS}" -ge "${deadline}" ]]; then
			status "still open; GitHub auto-merge stays armed"
			notify normal "PR #${number} still open" "Auto-merge stays armed. ${title}"
			exit 0
		fi
		sleep "${poll}"
	done
}

# Already merged (a rerun, or merged by hand) skips straight to cleanup.
state="$(pr_state)"
if ! settled "${state}"; then
	await_ci
	merge
fi
[[ "${state}" == MERGED ]] || fail "closed without merging"

mark_tab "#2f8f46" merged
notify normal "PR #${number} merged" "${title}"
if [[ "${from_fork}" == true ]]; then
	status "merged; its branch lives in a fork, so nothing here to clean up"
	exit 0
fi
status "merged; cleaning up ${branch}"

# Clean up from the primary worktree: the branch's own worktree is going away.
cd "$(git rev-parse --path-format=absolute --git-common-dir)/.."
git fetch --prune --quiet origin || true
# Fast-forward the default branch where it is checked out: the merge lands
# locally, and that checkout's post-merge hooks run (dev-profile re-renders
# the live profile). Git itself refuses when local changes are in the way.
default_branch="$(gh repo view ${slug:+"${slug}"} --json defaultBranchRef --jq .defaultBranchRef.name)"
if [[ "$(git branch --show-current)" == "${default_branch}" ]]; then
	git merge --ff-only --quiet "origin/${default_branch}" || status "could not fast-forward ${default_branch}"
fi
merged="$(ghr pr view "${pr}" --json headRefOid --jq .headRefOid)"
# Delete the remote branch only while it still holds exactly what merged;
# commits pushed after the merge keep it alive.
if [[ "$(git ls-remote --heads origin "refs/heads/${branch}" | cut -f1)" == "${merged}" ]]; then
	git push --quiet --force-with-lease="refs/heads/${branch}:${merged}" --delete origin "${branch}" || true
fi
# shellcheck source=lib/sh/remove-merged.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/remove-merged.sh"
if git rev-parse --verify --quiet "refs/heads/${branch}" >/dev/null; then
	remove_merged "${branch}" "${merged}" || fail "merged; kept ${branch} (see above)"
fi
status "merged and cleaned up"
