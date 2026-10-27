# herdr.zsh — Herdr tab creation and agent job tracking.

# Create a Herdr tab and submit a command to its interactive shell.
# Available in every Zsh session, including outside Herdr.
#
# Usage:
#   htab -- omp --resume <session-id>
htab() {
	emulate -L zsh

	if [[ "$1" != "--" || $# -lt 2 ]]; then
		print -u2 "Usage: htab -- <command> [args...]"
		return 2
	fi
	shift

	# Preserve argument boundaries and shell escaping.
	local cmd="" arg response pane_id
	for arg in "$@"; do
		cmd+="${(q)arg} "
	done

	# Create a focused tab in the current directory.
	response=$(herdr tab create --cwd "$PWD" --label "$1" --focus) || return 1
	pane_id=$(jq -er '.result.root_pane.pane_id' <<<"$response") || return 1

	# Submit the command to the interactive shell.
	herdr pane run "$pane_id" "${cmd% }"
}

# The remaining functions only apply inside Herdr.
[[ $HERDR_ENV == 1 && -n $HERDR_PANE_ID ]] || return 0

# Herdr tracks one agent identity per pane. When multiple agents are
# suspended with Ctrl+Z, the reported identity may become stale.
#
# Override fg to report the resumed agent before foregrounding it,
# then release that report when the job stops or exits.
#
# Use a separate source (zsh-fg) to avoid collisions with native
# Herdr integration sequence numbers.
#
# Only recognized agent jobs are reported. Other jobs resume normally.
# Bare %1 bypasses this function because Zsh provides no hook for it.

# Supported Herdr agent kinds.
typeset -ga _HERDR_AGENT_KINDS=(
	pi claude codex gemini cursor devin agy cline omp mastracode opencode
	copilot kimi kiro droid amp grok hermes kilo qodercli qwen letta maki muse
)

# Identify the agent kind associated with a Zsh job.
# Argument: optional job specification (defaults to current job).
_herdr_job_agent() {
	local line word

	line=$(jobs "${1:-%+}" 2>/dev/null) || return 1
	[[ $line =~ '^\[([0-9]+)\]' ]] || return 1

	for word in ${(z)jobtexts[$match[1]]}; do
		case $word in
		command | exec | env | nohup | builtin | *=*)
			continue
			;;
		esac

		word=${word:t}
		((${_HERDR_AGENT_KINDS[(Ie)$word]})) && print -r -- "$word"
		return 0
	done
}

# Foreground jobs while keeping Herdr's reported agent in sync.
fg() {
	local spec kind status_code=0

	for spec in "${@:-%+}"; do
		# Report the agent before resuming its job.
		kind=$(_herdr_job_agent "$spec")

		if [[ -n $kind ]]; then
			herdr pane report-agent "$HERDR_PANE_ID" \
				--source zsh-fg \
				--agent "$kind" \
				--state unknown &>/dev/null
		fi

		# Resume the requested job using Zsh's builtin.
		builtin fg "$spec"
		status_code=$?

		# Release the temporary identity after the job stops or exits.
		if [[ -n $kind ]]; then
			herdr pane release-agent "$HERDR_PANE_ID" \
				--source zsh-fg \
				--agent "$kind" &>/dev/null &!
		fi
	done

	return $status_code
}
