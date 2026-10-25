# herdr.zsh — make `fg` tell herdr which agent it is resuming.
#
# Herdr tracks one agent identity per pane, and an agent suspended with Ctrl+Z
# only keeps its integration-reported state until it speaks again. With two
# agents suspended in one pane, `fg` resumes one while herdr still shows the
# other (or nothing). So `fg` reports the resumed job's agent to the pane
# first, under its own source (`zsh-fg`) so it never collides with the
# integrations' `herdr:<agent>` sequence numbers, and releases that report
# once the job stops or exits so the label cannot outlive the process.
#
# Only jobs whose command is a herdr agent kind are reported; every other job
# resumes untouched. Bare `%1` bypasses this function (zsh has no hook for it).

[[ $HERDR_ENV == 1 && -n $HERDR_PANE_ID ]] || return 0

# Kinds from `herdr agent`; the label herdr expects is the command name.
typeset -ga _HERDR_AGENT_KINDS=(
	pi claude codex gemini cursor devin agy cline omp mastracode opencode
	copilot kimi kiro droid amp grok hermes kilo qodercli qwen letta maki muse
)

# Prints the agent kind of the job `$1` names (a jobspec; default current), or
# nothing when that job is not a herdr agent.
_herdr_job_agent() {
	local line word
	line=$(jobs "${1:-%+}" 2>/dev/null) || return 1
	[[ $line =~ '^\[([0-9]+)\]' ]] || return 1
	for word in ${(z)jobtexts[$match[1]]}; do
		case $word in
		command | exec | env | nohup | builtin | *=*) continue ;;
		esac
		word=${word:t}
		((${_HERDR_AGENT_KINDS[(Ie)$word]})) && print -r -- $word
		return 0
	done
}

fg() {
	local spec kind status_code=0
	for spec in "${@:-%+}"; do
		kind=$(_herdr_job_agent "$spec")
		[[ -n $kind ]] && herdr pane report-agent "$HERDR_PANE_ID" \
			--source zsh-fg --agent "$kind" --state unknown &>/dev/null
		builtin fg "$spec"
		status_code=$?
		[[ -n $kind ]] && {
			herdr pane release-agent "$HERDR_PANE_ID" \
				--source zsh-fg --agent "$kind" &>/dev/null &!
		}
	done
	return $status_code
}
