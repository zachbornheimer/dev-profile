# 01-output.zsh — `__`, the one formatter for status messages. Numbered so it is
# defined before any other module can print while it loads.
#
#   __ MESSAGE                        neutral, stdout
#   __ -t TYPE MESSAGE                typed; MESSAGE is never parsed as JSON
#   __ -o stdout|stderr ...           force the stream (do not redirect `__` itself)
#   __ '{"type":TYPE,"message":MESSAGE}'
#   __ -t pending MESSAGE -- CMD...   spinner while CMD runs, then a final line
#   __ '{"type":"pending",...}' -- CMD...
#
# TYPE is success (✔ green), failed (✘ red), warn (⚠ yellow) or neutral. failed
# and warn go to stderr, the rest to stdout, unless -o says otherwise. Color only
# reaches a terminal and stays off under NO_COLOR. JSON needs jq; JSON without a
# type is neutral.
#
# A pending message runs CMD (a command or a shell function) in the background
# while gum draws a blue minidot spinner on stderr, then replaces the spinner with
# the route its exit status picks from onComplete:
#
#   {"type": "pending", "message": "Processing...", "onComplete": {
#     "success": {"type": "success", "message": "Done!"},
#     "failed":  {"type": "failed",  "message": "Failed (%e)"},
#     "warning": {"type": "warn",    "message": "Deprecated.", "codes": [2]}}}
#
# Status 0 is success; a status in warning.codes (default [2], only when a warning
# route exists) is warning; any other is failed. %e is the exit status. A missing
# route prints MESSAGE (success) or "MESSAGE (exit N)". CMD's captured stdout and
# stderr follow the final line, and `__` returns CMD's status. Without a terminal
# on stderr, or without gum, CMD runs in the foreground with no spinner.

typeset -g _c_reset=$'\e[0m' _c_red=$'\e[31m' _c_green=$'\e[32m' _c_yellow=$'\e[33m' _c_blue=$'\e[34m'

__() {
	emulate -L zsh
	setopt no_monitor no_notify

	local type=neutral message spec='{}' stream=
	local -a fields

	while [[ ${1-} == -* && ${1-} != -- ]]; do
		case $1 in
		-t)
			if (($# < 2)); then
				__::render failed "usage: __ [-o stdout|stderr] [-t TYPE] MESSAGE [-- CMD...]"
				return 2
			fi
			type=$2
			shift 2
			;;
		-o)
			if [[ ${2-} != stdout && ${2-} != stderr ]]; then
				__::render failed "usage: __ [-o stdout|stderr] [-t TYPE] MESSAGE [-- CMD...]"
				return 2
			fi
			stream=$2
			shift 2
			;;
		*)
			__::render failed "usage: __ [-o stdout|stderr] [-t TYPE] MESSAGE [-- CMD...]"
			return 2
			;;
		esac
	done

	if (($# == 0)); then
		__::render failed "usage: __ [-o stdout|stderr] [-t TYPE] MESSAGE [-- CMD...]"
		return 2
	elif [[ -z $type || $type == neutral ]] && [[ $1 == '{'* ]]; then
		if ((!$+commands[jq])); then
			__::render failed "__: jq is required for JSON messages"
			return 127
		fi
		fields=("${(@Q)${(z)$(jq -er 'select(type == "object")
			| [.type // "neutral", .message // ""] | @sh' <<<"$1" 2>/dev/null)}}")
		if ((${#fields} == 2)); then
			spec=$1 type=$fields[1] message=$fields[2]
		else
			message=$1
		fi
		shift
	else
		message=$1
		shift
	fi

	if [[ $type == pending ]]; then
		if [[ ${1-} != -- || $# -lt 2 ]]; then
			__::render failed "__: a pending message needs -- CMD..."
			return 2
		fi
		shift
		__::pending "$spec" "$message" "$stream" "$@"
		return
	fi
	if (($#)); then
		__::render failed "__: only a pending message runs a command"
		return 2
	fi
	__::render "$type" "$message" "$stream"
}

# Prints one message line. $3, when set, is stdout or stderr and wins over the type.
__::render() {
	local icon color stream=${3-}
	local -i fd=1
	case $1 in
	success) icon='✔' color=$_c_green ;;
	failed | failure) icon='✘' color=$_c_red fd=2 ;;
	warn | warning) icon='⚠' color=$_c_yellow fd=2 ;;
	neutral) ;;
	*)
		print -ru2 -- "__: unknown message type: $1"
		return 2
		;;
	esac
	case $stream in
	stdout) fd=1 ;;
	stderr) fd=2 ;;
	esac

	if [[ -z $icon ]]; then
		print -ru$fd -- "$2"
	elif [[ -t $fd && -z ${NO_COLOR-} ]]; then
		print -ru$fd -- "$color$icon$_c_reset $2"
	else
		print -ru$fd -- "$icon $2"
	fi
}

# Runs CMD under the spinner, then renders the onComplete route for its status.
# $3 is the -o stream, forwarded to the final line.
__::pending() {
	local spec=$1 message=$2 stream=$3
	shift 3
	local out err
	local -i code pid=0

	if [[ -t 2 ]] && (($+commands[gum])); then
		out=$(mktemp) err=$(mktemp)
		{
			"$@" >"$out" 2>"$err" &
			pid=$!
			# gum owns the animation and the terminal; it waits on the pid, not the
			# command, so CMD can be a shell function.
			if gum spin --spinner minidot --spinner.foreground 4 --title "$message" -- \
				sh -c 'while kill -0 "$1" 2>/dev/null; do sleep 0.05; done' sh "$pid"; then
				wait $pid
				code=$?
				pid=0
			else
				code=130
			fi
			__::route "$spec" "$message" $code "$stream"
			cat -- "$out"
			cat -- "$err" >&2
		} always {
			# Ctrl-C ends gum (or aborts this function); CMD ignores SIGINT as a
			# background job, so stop it and the commands it started.
			if ((pid)); then
				pkill -P $pid 2>/dev/null
				kill $pid 2>/dev/null
				wait $pid 2>/dev/null
			fi
			rm -f -- "$out" "$err"
		}
	else
		"$@"
		code=$?
		__::route "$spec" "$message" $code "$stream"
	fi
	return $code
}

# Renders the onComplete route that exit status $3 selects.
__::route() {
	local -a fields
	if ((!$+commands[jq])); then
		if (($3 == 0)); then
			__::render success "$2" "$4"
		else
			__::render failed "$2 (exit $3)" "$4"
		fi
		return
	fi
	fields=("${(@Q)${(z)$(jq -r --arg fallback "$2" --argjson code "$3" '
		(.onComplete // {}) as $on
		| ($on.warning.codes // (if $on.warning then [2] else [] end)) as $warn
		| (if $code == 0 then "success"
			elif ($warn | index($code)) then "warning"
			else "failed" end) as $key
		| ($on[$key] // {}) as $route
		| [$route.type // $key,
			($route.message // (if $key == "success" then $fallback
										else "\($fallback) (exit %e)" end)
				| tostring | gsub("%e"; $code | tostring))]
		| @sh' <<<"$1")}}")
	__::render "$fields[1]" "$fields[2]" "$4"
}
