# within — run a command under a deadline.
#
#   within 1s -- true
#   within 30s -- grok --single 'Respond with exactly pong' --output-format json
#   within 30s -- 'grok --single "Respond with exactly pong" --output-format json | jq -e ".text == \"pong\""'
#
# Units: d, h, m (minutes), s, ms. A pipe is shell syntax, so a pipeline has
# to be one quoted argument — the shell binds `|` before within runs.

within::usage() {
	__ -t failed "usage: within <duration> -- <command>"
	__ -o stderr "duration: <n><d|h|m|s|ms>    e.g. 1s, 5m, 2h, 1d, 500ms"
	__ -o stderr "quote pipelines: within 1s -- 'cmd | other'"
}

# Print a GNU timeout duration, or fail. ms becomes fractional seconds.
within::duration() {
	emulate -L zsh
	local spec=$1 unit n
	case $spec in
	*ms)
		unit=ms
		n=${spec%ms}
		;;
	*s)
		unit=s
		n=${spec%s}
		;;
	*m)
		unit=m
		n=${spec%m}
		;;
	*h)
		unit=h
		n=${spec%h}
		;;
	*d)
		unit=d
		n=${spec%d}
		;;
	*)
		__ -t failed "within: bad duration '$spec' (want <n><d|h|m|s|ms>)"
		return 1
		;;
	esac
	if [[ $n != <-> && $n != <->.<-> ]]; then
		__ -t failed "within: bad duration '$spec' (want <n><d|h|m|s|ms>)"
		return 1
	fi
	if ((n == 0)); then
		__ -t failed "within: duration must be greater than 0"
		return 1
	fi
	if [[ $unit == ms ]]; then
		printf '%.6f\n' $((n / 1000.0))
		return 0
	fi
	builtin print -r -- "$spec"
}

# Print alias and function defs the child shell needs in order to run $1.
# `seen` is dynamically scoped from within::prelude.
within::define() {
	emulate -L zsh
	local word name
	for word in ${(z)1}; do
		name=${(Q)word}
		[[ -n $name && -z $seen[$name] ]] || continue
		seen[$name]=1
		if [[ -n $aliases[$name] ]]; then
			alias -L -- "$name"
			within::define "$aliases[$name]"
		elif ((${+functions[$name]})); then
			typeset -f -- "$name"
			within::define "$functions[$name]"
		fi
	done
}

within::prelude() {
	emulate -L zsh
	zmodload zsh/parameter
	local -A seen
	within::define "$1"
}

within::verdict() {
	if (($1 == 0)); then
		__ -t success Passed
		return 0
	fi
	__ -o stdout -t failed Failed
	return 1
}

within() {
	emulate -L zsh
	setopt local_options

	if (($# < 3)) || [[ $2 != -- ]]; then
		within::usage
		return 1
	fi

	local spec=$1
	shift 2

	local duration script prelude rc=0
	local -r kill_grace=${WITHIN_KILL_GRACE:-0.5}
	duration=$(within::duration "$spec") || return 1

	if ! command -v timeout >/dev/null 2>&1; then
		__ -t failed "within: timeout not found (brew install coreutils)"
		return 1
	fi

	if (($# == 1)); then
		script=$1
	else
		script="${(j: :)${(q)@}}"
	fi

	prelude=$(within::prelude "$script") || prelude=

	command timeout --kill-after="$kill_grace" "$duration" \
		zsh -o aliases -o pipefail -c 'eval "$1" && eval "$2"' \
		within "$prelude" "$script"
	rc=$?
	within::verdict "$rc"
}
