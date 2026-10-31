#!/usr/bin/env bash
# One-shot omp prompt for herdr.
#
# Bound to a herdr popup key command (see config.toml). Asks for a prompt and
# an omp model level (@default, @smol, or @slow), then opens a new tab in the
# dedicated `one-shots` herdr session (same cwd, focus unchanged; the session
# server is started headless if it is down)
# and runs an interactive `omp` there with the prompt as its first message, so
# the pane stays open for follow-ups. The omp session is saved, so history stays
# resumable. The tab is closed once it has been unused for ONESHOT_TTL_SECONDS
# (default 24h): "used" means its output changed or its agent is working/blocked
# since the last reap.
#
#   oneshot.sh           interactive (popup): prompt + model level via gum
#   oneshot.sh --reap    close unused tabs only (run by launchd)
#
# Test hooks: ONESHOT_PROMPT / ONESHOT_MODEL skip the gum prompts ("" omits
# --model, same as starting on @default); ONESHOT_IS_ONE_SHOT=yes|no skips the
# "is this a 1-shot prompt?" question (no = focused, never-reaped tab in the
# invoking session's active workspace instead of the one-shots session);
# ONESHOT_SESSION names the herdr session; ONESHOT_DIR, ONESHOT_TTL_SECONDS.
set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"
DIR="${ONESHOT_DIR:-$HOME/.config/herdr/oneshot}"
STATE="$DIR/panes.tsv"
TTL="${ONESHOT_TTL_SECONDS:-86400}"
SESSION="${ONESHOT_SESSION:-one-shots}"
SOCKET="$HOME/.config/herdr/sessions/$SESSION/herdr.sock"
# omp model levels. The popup asks which one to start on; the choice is passed
# as --model @default|@smol|@slow.
MODELS=(@default @smol @slow)

mkdir -p "$DIR"
touch "$STATE"

# Run a herdr command against the server behind socket $1. The socket is explicit
# because popups and launchd inherit HERDR_SOCKET_PATH for the default session.
hd() {
	local socket=$1
	shift
	HERDR_SOCKET_PATH="$socket" "$HERDR" "$@"
}

# Hash of a pane's recent output, minus omp's footer. Interactive omp redraws
# its footer (input box, model/context line, live status-board counts) while
# idle, so hashing it would mark every tab as used on every reap. The footer
# starts at the second-to-last line that opens with a ─ rule; output without
# two rules (a plain shell after omp exits) is hashed whole.
pane_digest() {
	hd "$1" pane read "$2" --source recent-unwrapped --lines 200 2>/dev/null |
		awk '{ l[NR] = $0 } /^──────────/ { r2 = r1; r1 = NR }
      END { n = r2 ? r2 - 1 : NR; for (i = 1; i <= n; i++) print l[i] }' |
		shasum | cut -d' ' -f1
}

# State rows: <last-active-epoch> TAB <output-hash|-> TAB <socket> TAB <tab-id>
# TAB <prompt-file>. Tab ids are never reused, so closing a stale id cannot hit
# someone else's tab.
reap() {
	local now keep active hash socket tab file list info pane status current
	now=$(date +%s)
	keep=$(mktemp)
	while IFS=$'\t' read -r active hash socket tab file; do
		[ -n "$active" ] || continue
		if list=$(hd "$socket" pane list 2>/dev/null); then
			info=$(jq -r --arg t "$tab" \
				'[.result.panes[] | select(.tab_id == $t)][0] | select(. != null) | [.pane_id, .agent_status] | @tsv' \
				<<<"$list")
			if [ -z "$info" ]; then # tab already closed by hand
				rm -f "$file"
				continue
			fi
			IFS=$'\t' read -r pane status <<<"$info"
			current=$(pane_digest "$socket" "$pane") || current=$hash
			if [ "$current" != "$hash" ] || [ "$status" = working ] || [ "$status" = blocked ]; then
				active=$now
				hash=$current
			fi
		fi # server unreachable: activity unknown, so only the stored timestamp counts
		if [ $((now - active)) -ge "$TTL" ]; then
			hd "$socket" tab close "$tab" >/dev/null 2>&1 || true
			rm -f "$file"
		else
			printf '%s\t%s\t%s\t%s\t%s\n' "$active" "$hash" "$socket" "$tab" "$file" >>"$keep"
		fi
	done <"$STATE"
	mv "$keep" "$STATE"
}

# Start the named session's headless server when it is not already answering.
ensure_session() {
	hd "$SOCKET" workspace list >/dev/null 2>&1 && return 0
	(
		cd "$HOME" && env -u HERDR_SOCKET_PATH nohup "$HERDR" --session "$SESSION" server \
			>/dev/null 2>&1 &
	)
	local _
	for _ in $(seq 40); do
		hd "$SOCKET" workspace list >/dev/null 2>&1 && return 0
		sleep 0.25
	done
	echo "herdr session '$SESSION' did not start" >&2
	return 1
}

if [ "${1:-}" = "--reap" ]; then
	reap
	exit 0
fi

reap

prompt="${ONESHOT_PROMPT:-}"
# ctrl+e in gum write opens $EDITOR: always nvim here, with the file explorer
# suppressed (see NVIM_NO_EXPLORER in nvim's zach/core/explorer.lua).
export EDITOR=nvim NVIM_NO_EXPLORER=1

if [ -z "$prompt" ]; then
	prompt=$(gum write --header "prompt (ctrl+j = newline, ctrl+e = editor, enter = submit, esc = cancel)" \
		--placeholder "one-shot prompt" --width 0 --height 8) || exit 0
fi
[ -n "$prompt" ] || exit 0

# One-shot (default): a tab in the dedicated one-shots session, reaped when
# unused. Not one-shot: a focused tab in the invoking (default) session's active
# workspace, never reaped, so the omp session stays open.
if [ -z "${ONESHOT_IS_ONE_SHOT+x}" ]; then
	one_shot=$(gum choose --header "is this a 1-shot prompt?" --selected yes yes no) || exit 0
else
	one_shot="$ONESHOT_IS_ONE_SHOT"
fi

if [ -z "${ONESHOT_MODEL+x}" ]; then
	model=$(gum choose --header "model level" "${MODELS[@]}") || exit 0
else
	model="$ONESHOT_MODEL"
fi

cwd="${HERDR_ACTIVE_PANE_CWD:-$PWD}"
now=$(date +%s)

if [ "$one_shot" = no ]; then
	SOCKET="${HERDR_SOCKET_PATH:-$HOME/.config/herdr/herdr.sock}"
	workspace="${HERDR_ACTIVE_WORKSPACE_ID:-$(hd "$SOCKET" workspace list | jq -er '.result.workspaces[0].workspace_id')}"
	label_prefix="omp"
	focus=--focus
else
	ensure_session
	workspace=$(hd "$SOCKET" workspace list | jq -er '.result.workspaces[0].workspace_id')
	label_prefix="oneshot"
	focus=--no-focus
fi

# `pane run` rejects command lines over the macOS canonical-input limit, so the
# prompt travels in a file (omp reads `@file` as the message).
file="$DIR/prompt-$now-$$.md"
printf '%s\n' "$prompt" >"$file"

first_line="${prompt%%$'\n'*}"
created=$(hd "$SOCKET" tab create --workspace "$workspace" --cwd "$cwd" \
	--label "$label_prefix: ${first_line:0:24}" "$focus")
tab=$(jq -er '.result.tab.tab_id' <<<"$created")
pane=$(jq -er '.result.root_pane.pane_id' <<<"$created")
[ "$one_shot" = no ] || printf '%s\t-\t%s\t%s\t%s\n' "$now" "$SOCKET" "$tab" "$file" >>"$STATE"

cmd="omp"
[ -z "$model" ] || cmd+=" --model $(printf '%q' "$model")"
cmd+=" @$(printf '%q' "$file")"

hd "$SOCKET" pane run "$pane" "$cmd" >/dev/null
