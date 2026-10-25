#!/usr/bin/env bash
# `__` (shell/zsh/01-output.zsh): each message type reaches its stream with its
# icon, and a pending message routes on its command's exit status. No terminal
# here, so the spinner path is skipped and output carries no color.
set -euo pipefail

module="$(cd "$(dirname "$0")/.." && pwd -P)/shell/zsh/01-output.zsh"

fail() {
	echo "FAIL output fixture: $*" >&2
	exit 1
}

# Runs zsh code with the module loaded; prints "stdout|stderr|status".
run() {
	local out err code=0
	err="$(mktemp)"
	out="$(MODULE="${module}" zsh -f -c 'source "$MODULE"; '"$1" 2>"${err}")" || code=$?
	printf '%s|%s|%s' "${out}" "$(<"${err}")" "${code}"
	rm -f "${err}"
}

expect() {
	local got
	got="$(run "$1")"
	[[ "${got}" == "$2" ]] || fail "$1: expected [$2], got [${got}]"
}

expect '__ "plain {text}"' 'plain {text}||0'
expect "__ '{\"message\":\"json\"}'" 'json||0'
expect "__ '{not json'" '{not json||0'
expect "__ '{\"type\":\"success\",\"message\":\"it'\\''s \\\"done\\\"\"}'" "✔ it's \"done\"||0"
expect '__ -t success "{\"type\":\"failed\"}"' '✔ {"type":"failed"}||0'
expect '__ -t failed "broke"' '|✘ broke|0'
expect '__ -t warn "careful"' '|⚠ careful|0'
expect '__ -o stdout -t failed "on out"' '✘ on out||0'
expect '__ -t success -o stderr "on err"' '|✔ on err|0'
expect '__ -o nope x' '|✘ usage: __ [-o stdout|stderr] [-t TYPE] MESSAGE [-- CMD...]|2'
expect '__ -t bogus x' '|__: unknown message type: bogus|2'
expect '__ -t success x -- true' '|✘ __: only a pending message runs a command|2'
expect '__ -t pending x' '|✘ __: a pending message needs -- CMD...|2'

# Pending: the command runs (a shell function works), its output passes through,
# and the route follows the exit status, which `__` returns.
routes='{"type":"pending","message":"Working","onComplete":{
	"success":{"type":"success","message":"Done!"},
	"failed":{"type":"failed","message":"Failed %e"},
	"warning":{"type":"warn","message":"Deprecated."}}}'
job='job() { print out; print err >&2; return $1 }; '
expect "${job}__ '${routes}' -- job 0" $'out\n✔ Done!|err|0'
expect "${job}__ '${routes}' -- job 2" $'out|err\n⚠ Deprecated.|2'
expect "${job}__ '${routes}' -- job 7" $'out|err\n✘ Failed 7|7'
expect "__ '{\"type\":\"pending\",\"message\":\"W\",\"onComplete\":{\"warning\":{\"message\":\"warned %e\",\"codes\":[3]}}}' -- sh -c 'exit 3'" '|⚠ warned 3|3'
expect '__ -t pending "Copying" -- true' '✔ Copying||0'
expect '__ -t pending "Copying" -- false' '|✘ Copying (exit 1)|1'
expect '__ -t pending "Copying" -- sh -c "exit 2"' '|✘ Copying (exit 2)|2'
echo "output fixture ok"
