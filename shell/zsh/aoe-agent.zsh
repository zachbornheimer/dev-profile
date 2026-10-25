# agent / a — start a coding agent as an aoe ACP structured-view session, then open the dashboard.
#   agent <auto|ACP agent> [--model <m>] [--effort <e>] [--resume <id>] [prompt...]
#   agent grok:<uuid>   (also claude:  claude-code:  codex:  opencode:)
# `auto` omits --agent so aoe uses its default ACP agent.
# A `harness:id` or `--resume harness:id` restores that native ACP conversation in its cwd.
# If that session already has a title, it is passed as `aoe add --title`.
# Options are validated before any session is created, so bad input never leaves an orphan.

typeset -g AOE_DEFAULT_EFFORT=medium
# Fresh Claude sessions use an initial /effort command; native resume uses explicit --effort.
typeset -ga AOE_EFFORT_AGENTS=(claude claude-code)
# grok is a custom ACP agent via ~/.agent-of-empires/config.toml [session.agent_acp_cmd].
typeset -ga AOE_ACP_AGENTS=(claude claude-code grok codex opencode aoe-agent gemini kimi omp pi prime-agent vibe)
typeset -g AOE_FIND_SESSION="$HOME/.agents/available-skills/find-session/scripts/find-session.py"
typeset -g AOE_FIND_TRANSCRIPT="$HOME/.agents/available-skills/assume-session/scripts/find-transcript.sh"
typeset -g AOE_EXTRACT_CONTEXT="$HOME/.agents/available-skills/assume-session/scripts/extract-context.py"
typeset -g AOE_SESSION_FACTS="${${(%):-%x}:h}/aoe-session-facts.py"

# The daemon spawns the worker after `aoe add` returns; a prompt sent before then
# fails with "not found on the daemon". Retry ~30s total (60 x 0.5s), only for that error.
# Sleep between tries, not after the last failure.
typeset -gi AOE_PROMPT_ATTEMPTS=60
typeset -g AOE_PROMPT_DELAY_SECS=0.5
typeset -g AOE_PROMPT_NOT_READY='not found on the daemon'

export AOE_HOOK_BIN="${AOE_HOOK_BIN-}"
export AOE_INSTANCE_ID="${AOE_INSTANCE_ID-}"

agent::usage() {
	cat <<EOF
usage: agent <harness|harness:id|--resume harness:id> [--model <m>] [--effort <e>] [--resume <id>] [prompt...]      (alias: a)

  harness     auto | ${(j: | :)AOE_ACP_AGENTS}
              "auto" uses aoe's default ACP agent.
  harness:id  resume that CLI session in ACP (grok: claude: claude-code: codex: opencode:)
              restores the original native conversation and creates the AoE view in that cwd.
              an existing title on that session is passed as $(aoe add --title).
  --model     forwarded to the agent.
  --effort    explicit ACP effort on resume; fresh Claude sessions default to ${AOE_DEFAULT_EFFORT}.
  --resume    accepts harness:id first, or a native id after the harness.
  prompt      sent after successful native restore, or as the first fresh-session message.

Loads AI keys (ai-keys::env), unsets TMUX so AoE does not attach to Gas City, and opens \`aoe url\`.
EOF
}

# True when $1 is a harness:id token (no spaces, not an option).
agent::is-session-ref() {
	[[ -n ${1:-} && $1 != -* && $1 == *:* && $1 != *[[:space:]]* ]]
}

# Sets reply=(harness model effort resume_ref prompt). Returns 2 before any session exists.
# A harness:id or --resume sets resume_ref. A bare resume id is prefixed with the harness
# unless the harness is auto. Effort is the default only for effort agents.
agent::parse-args() {
	local harness model effort resume_ref prompt requested_effort
	if (($# == 0)); then
		__ -t failed "agent: harness required"
		return 2
	fi
	if [[ $1 == --resume ]]; then
		if (($# < 2)) || ! agent::is-session-ref "$2"; then
			__ -t failed 'agent: leading --resume needs harness:id'
			return 2
		fi
		shift
	fi
	if agent::is-session-ref "$1"; then
		resume_ref=$1
		harness=${1%%:*}
	else
		harness=$1
	fi
	shift
	if [[ $harness != auto ]] && ((!${AOE_ACP_AGENTS[(Ie)$harness]})); then
		__ -t failed "agent: '$harness' is not an ACP agent. Valid: auto ${AOE_ACP_AGENTS}"
		return 2
	fi
	while (($#)) && [[ $1 == -* && $1 != *[[:space:]]* ]]; do
		case $1 in
		--model | --resume | --effort)
			if (($# < 2)); then
				__ -t failed "agent: $1 needs a value"
				return 2
			fi
			case $1 in
			--model) model=$2 ;;
			--resume) resume_ref=$2 ;;
			--effort) requested_effort=$2 ;;
			esac
			shift 2
			;;
		*)
			__ -t failed "agent: unknown option '$1'. Valid options: --model <m>, --effort <e>, --resume <id>, -h/--help"
			return 2
			;;
		esac
	done
	if [[ -n $resume_ref && $resume_ref != *:* && $harness != auto ]]; then
		resume_ref="${harness}:$resume_ref"
	fi
	if [[ -n $resume_ref ]]; then
		if [[ $resume_ref != *:* || ${resume_ref%%:*} != $harness || -z ${resume_ref#*:} ]]; then
			__ -t failed 'agent: resume reference must name the selected harness and a native id'
			return 2
		fi
		effort=$requested_effort
	elif ((${AOE_EFFORT_AGENTS[(Ie)$harness]})); then
		effort=${requested_effort:-$AOE_DEFAULT_EFFORT}
	elif [[ -n $requested_effort ]]; then
		__ -t failed 'agent: fresh-session --effort is supported for Claude only'
		return 2
	fi
	prompt=${(j: :)*}
	reply=("$harness" "$model" "$effort" "$resume_ref" "$prompt")
}

# Sets reply=(cwd title). Empty title is success. The directory must already exist.
agent::session-facts() {
	local ref=$1 out cwd title
	reply=("" "")
	out=$(python3 "$AOE_SESSION_FACTS" "$ref" "$AOE_FIND_SESSION" "$AOE_FIND_TRANSCRIPT" "$AOE_EXTRACT_CONTEXT") || return $?
	cwd=$out
	if [[ $out == *$'\n'* ]]; then
		cwd=${out%%$'\n'*}
		title=${out#*$'\n'}
		title=${title%%$'\n'*}
	fi
	reply=("$cwd" "$title")
	if [[ ! -d $cwd ]]; then
		__ -t failed "agent: could not resolve an existing directory for $ref"
		return 1
	fi
}

# Sets reply to the aoe add command. The project path is included only when resuming.
agent::add-argv() {
	local harness=$1 model=$2 title=$3 project=$4 resume_ref=$5 effort=${6:-}
	reply=(aoe add --structured-view)
	[[ $harness != auto ]] && reply+=(--agent "$harness")
	[[ -n $model ]] && reply+=(--model "$model")
	[[ -n $title ]] && reply+=(--title "$title")
	[[ -n $resume_ref ]] && reply+=(--resume "${resume_ref#*:}")
	[[ -n $resume_ref && -n $effort ]] && reply+=(--effort "$effort")
	[[ -n $resume_ref && -n $project ]] && reply+=("$project")
}

# Sources ai-keys::env with allexport. Missing helper is fine; a bad path is not.
agent::load-keys() {
	if ((!$+functions[ai-keys::env])); then
		return 0
	fi
	local keys_env
	keys_env=$(ai-keys::env) || return 1
	if [[ ! -f $keys_env || ! -r $keys_env ]]; then
		__ -t failed "agent: ai-keys::env did not return a readable file"
		return 1
	fi
	setopt localoptions allexport
	source "$keys_env"
}

# Delivers one prompt. Retries only while the worker is not on the daemon yet.
agent::send-prompt() {
	local session_id=$1 prompt=$2 out
	local resend="  aoe acp prompt $session_id -- ${(qq)prompt}"
	local -i attempt
	for ((attempt = 1; attempt <= AOE_PROMPT_ATTEMPTS; attempt++)); do
		out=$(aoe acp prompt "$session_id" -- "$prompt" 2>&1) && return 0
		if [[ $out != *$AOE_PROMPT_NOT_READY* ]]; then
			__ -t failed "agent: prompt failed for session $session_id; resend with:"$'\n'"$resend"$'\n'"$out"
			return 1
		fi
		if ((attempt < AOE_PROMPT_ATTEMPTS)); then
			sleep "$AOE_PROMPT_DELAY_SECS"
		fi
	done
	__ -t failed "agent: session $session_id worker never started; resend with:"$'\n'"$resend"
	return 1
}

# Wait for successful native load before sending optional text.
agent::wait-resume() {
	local session_id=$1 native_id=$2 output
	local -i attempt outcome
	for ((attempt = 1; attempt <= AOE_PROMPT_ATTEMPTS; attempt++)); do
		output=$(aoe acp history "$session_id" --json 2>&1) || {
			[[ $output == *$AOE_PROMPT_NOT_READY* ]] || {
				__ -t failed "$output"
				return 1
			}
			output=
		}
		print -r -- "$output" | python3 -c '
import json, sys
native = sys.argv[1]
for line in sys.stdin:
    try:
        event = json.loads(line).get("event", {})
    except (ValueError, AttributeError):
        continue
    failure = event.get("AgentStartupError")
    assigned = event.get("AcpSessionAssigned")
    if event.get("kind") == "agent_startup_error":
        failure = event
    if event.get("kind") == "acp_session_assigned":
        assigned = event
    if isinstance(failure, dict):
        print(failure.get("message", "native restore failed"), file=sys.stderr)
        sys.exit(1)
    if isinstance(assigned, dict):
        sys.exit(0 if assigned.get("acp_session_id") == native else 1)
sys.exit(2)
' "$native_id"
		outcome=$?
		((outcome == 0)) && return 0
		((outcome == 1)) && return 1
		((attempt < AOE_PROMPT_ATTEMPTS)) && sleep "$AOE_PROMPT_DELAY_SECS"
	done
	__ -t failed "agent: native restore did not complete for $session_id; optional prompt was not sent"
	return 1
}

# Sets reply to the prompts launch sends, skipping empty effort, resume, and text.
agent::startup-prompts() {
	local effort=$1 resume_ref=$2 prompt=$3
	reply=()
	[[ -n $effort && -z $resume_ref ]] && reply+=("/effort $effort")
	[[ -n $prompt ]] && reply+=("$prompt")
}

# Creates the session, sends startup prompts, then opens the dashboard.
# Runs in a subshell so loaded keys and TMUX changes do not leak.
# A failed prompt stops later prompts, but the dashboard is still attempted.
agent::launch() {
	(
		local harness=$1 model=$2 effort=$3 resume_ref=$4 prompt=$5 project=$6 title=$7
		local output session_id where url message open_status
		local -i failed=0
		local -a cmd=() messages=()
		unset TMUX TMUX_PANE
		agent::load-keys || exit 1
		if [[ -n $resume_ref ]]; then
			local preflight
			preflight=$(aoe acp status __native_resume_preflight__ --json 2>&1) || {
				__ -t failed "agent: daemon preflight failed before session creation"$'\n'"$preflight"
				exit 1
			}
		fi
		agent::add-argv "$harness" "$model" "$title" "$project" "$resume_ref" "$effort"
		cmd=("${reply[@]}")
		if ! output=$("${cmd[@]}" 2>&1) || [[ ! $output =~ 'ID:[[:space:]]+([[:xdigit:]]+)' ]]; then
			__ -t failed "agent: aoe add failed for harness '$harness'"$'\n'"$output"
			exit 1
		fi
		session_id=$match[1]
		where=${project:-$PWD}
		if [[ -n $title ]]; then
			__ -t success "Added $harness session $session_id \"$title\" in ${where/#$HOME/~}"
		else
			__ -t success "Added $harness session $session_id in ${where/#$HOME/~}"
		fi
		if [[ -n $resume_ref ]]; then
			agent::wait-resume "$session_id" "${resume_ref#*:}" || failed=1
		fi
		agent::startup-prompts "$effort" "$resume_ref" "$prompt"
		messages=("${reply[@]}")
		((failed != 0)) && messages=()
		for message in "${messages[@]}"; do
			agent::send-prompt "$session_id" "$message" || {
				failed=$?
				break
			}
		done
		url=$(aoe url) || url=
		if [[ $url == http://* || $url == https://* ]]; then
			command open "$url" || {
				open_status=$?
				((failed == 0)) && failed=$open_status
			}
		else
			__ -t failed "agent: session $session_id exists, but aoe url failed"
			((failed == 0)) && failed=1
		fi
		exit $failed
	)
}

agent() {
	if (($# == 0)) || [[ $1 == (-h|--help|help) ]]; then
		agent::usage
		return $(($# == 0))
	fi
	if ! (($+commands[aoe])); then
		__ -t failed "agent: aoe not found on PATH (brew install aoe?)"
		return 127
	fi
	agent::parse-args "$@" || return $?
	local harness=$reply[1] model=$reply[2] effort=$reply[3] resume_ref=$reply[4] prompt=$reply[5]
	local project title
	if [[ -n $resume_ref ]]; then
		agent::session-facts "$resume_ref" || return $?
		project=$reply[1]
		title=$reply[2]
	fi
	agent::launch "$harness" "$model" "$effort" "$resume_ref" "$prompt" "$project" "$title"
}

# Short alias that survives any other `agent` on PATH or in a plugin.
a() { agent "$@"; }
