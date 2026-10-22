#!/usr/bin/env bash
# The world every dev-family fixture runs in, sourced by the files in this
# directory: the dev task family against real git and a stubbed portless. The
# `portless`, `php` and `aube` stubs mean no proxy, php, node or network is
# needed; the portless stub records every spawn, which is how a fixture proves
# one stack. Each file owns its world, so doctor runs them as a pool.
#
# The script tags every process a stack starts with the checkout's directory
# name, and reaping stops every process on the machine that carries that tag. So
# a checkout's directory name must be unique to one run of one file: two files
# (or two doctors) that both called a checkout `repo` would stop each other's
# stacks. `rn` is that name -- the file's name and this run's temporary
# directory -- and every checkout directory is built from it.
# Usage (sourced): . world.sh <generated-dir>
set -euo pipefail

# Sourced, never run: a fixture file that forgot to source this would otherwise
# look like a passing fixture that did nothing.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	echo 'world.sh is sourced by the dev-family fixture files in this directory; run those instead' >&2
	exit 2
fi

out="${1:?usage: <fixture>.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
dev="${out}/bin/dev-profile-dev"
cache="${work}/cache/dev-profile/dev"
suffix="$(basename "${work}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-')"
rn="dfx-$(basename "$0" .sh)-${suffix#tmp-}"
# Every stub and stack process carries it, so `ps eww` says whose it is.
export DEV_FIXTURE_NAME="${rn}"

fail() {
	echo "FAIL dev-family fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# Stop every process the stubs started and every stack a pidfile records, then
# drop the work tree. The pidfiles matter: a stack the fixture left running is
# still writing its log, and that writer racing the removal leaves the directory
# non-empty — so the removal retries briefly before giving up.
cleanup() {
	local pid pidfile
	if [[ -f "${DEV_FIXTURE_PIDS:-}" ]]; then
		while IFS= read -r pid; do
			kill -TERM "${pid}" 2>/dev/null || :
		done <"${DEV_FIXTURE_PIDS}"
	fi
	for pidfile in "${cache}"/*.pid; do
		[[ -e "${pidfile}" ]] || continue
		kill -TERM "$(sed -n 1p "${pidfile}")" 2>/dev/null || :
	done
	for _ in 1 2 3 4 5; do
		rm -rf "${work}" 2>/dev/null && return 0
		sleep 0.5
	done
}
trap cleanup EXIT

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
# One throwaway cache, so the fixture never touches the machine's dev state.
export XDG_CACHE_HOME="${work}/cache"
export DEV_FIXTURE_SPAWNS="${work}/spawns" DEV_FIXTURE_PIDS="${work}/pids" DEV_FIXTURE_ROUTES="${work}/routes"
: >"${DEV_FIXTURE_SPAWNS}"
: >"${DEV_FIXTURE_PIDS}"
: >"${DEV_FIXTURE_ROUTES}"
# Short waits: the fixture must not depend on production timings.
export DEV_PROFILE_DEV_SETTLE=0 DEV_PROFILE_DEV_READY_TIMEOUT=5 DEV_PROFILE_DEV_STOP_TIMEOUT=2

# The portless stub answers `get <name>` with the name as given, and for
# `run --name <name> <cmd>` assigns PORT and runs the command, recording each
# spawn. Real portless prefixes a git worktree's branch onto any name it is run
# in, so the stub refuses to run inside a git repo: the script must hand portless
# the whole host and keep portless out of the checkout.
mkdir -p "${work}/bin"
cat >"${work}/bin/portless" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if git rev-parse --git-dir >/dev/null 2>&1; then
	echo "portless stub: run inside a git repo, where real portless adds a worktree prefix" >&2
	exit 65
fi
if [[ "$1" == get ]]; then
	echo "https://$2.localhost"
	exit 0
fi
# `list` reports route holders in portless's normal output shape.
if [[ "$1" == list ]]; then
	[[ -f "${DEV_FIXTURE_ROUTES:-}" ]] && cat "${DEV_FIXTURE_ROUTES}"
	exit 0
fi
[[ "$1" == run && "$2" == --name ]] || { echo "portless stub: unexpected args: $*" >&2; exit 64; }
printf '%s\t%s\n' "$3" "$*" >>"${DEV_FIXTURE_SPAWNS}"
shift 3
export PORT=4611
exec "$@"
STUB
# php and aube stubs: an inferred command must "serve" without either tool.
for tool in php aube; do
	cat >"${work}/bin/${tool}" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$$" >>"${DEV_FIXTURE_PIDS}"
exec sleep 300
STUB
	chmod +x "${work}/bin/${tool}"
done
chmod +x "${work}/bin/portless"
export PATH="${work}/bin:${PATH}"

sleeper_serve() {
	printf '#!/usr/bin/env bash\nset -euo pipefail\nexec sleep 300\n' >"$1"
	chmod +x "$1"
}

run_dev() { "${dev}" "$@" >"${work}/output.txt" 2>&1; }

# Poll a command until it succeeds, for about 20 seconds.
wait_for() {
	local waited=0
	until "$@"; do
		((waited++ < 20)) || return 1
		sleep 1
	done
}

# The stub records a spawn when it starts, a moment after the script has seen the
# stack's pidfile and returned, so on a loaded machine the record lags the
# command that caused it. Wait for it before judging, or the assertion races a
# stub that has not started yet.
spawns() { awk 'END { print NR }' "${DEV_FIXTURE_SPAWNS}"; }

spawns_reach() { [[ "$(spawns)" -ge "$1" ]]; }

# Wait for <n> spawns, so that comparing the count exactly still catches a second
# stack once the record has caught up.
wait_spawns() { wait_for spawns_reach "$1" || :; }

has_spawn_name() { cut -f1 "${DEV_FIXTURE_SPAWNS}" | grep -qxF "$1"; }

expect() { grep -qE "$1" "${work}/output.txt" || fail "the output must match /$1/"; }

expect_spawn() { wait_for grep -qF -- "$1" "${DEV_FIXTURE_SPAWNS}" || fail "no spawn ran '$1'"; }

expect_spawn_name() { wait_for has_spawn_name "$1" || fail "no spawn for route '$1'"; }

lines() { awk 'END { print NR }' "$1"; }

# A repo whose composer.json and package.json dev script the script serves as
# the php and js pair.
pair_repo() { # <dir>
	git init -q -b main "$1"
	printf '{"require":{}}\n' >"$1/composer.json"
	printf '{"scripts":{"dev":"vite"}}\n' >"$1/package.json"
	git -C "$1" add -A
	git -C "$1" commit -qm pair
}

# dev:restart is the only verb that stops, so when the fixture needs a down
# stack it signals the recorded pid itself.
stop_stack() {
	if [[ -f "${cache}/$1.pid" ]]; then
		kill -TERM "$(sed -n 1p "${cache}/$1.pid")" 2>/dev/null || :
		rm -f "${cache}/$1.pid"
	fi
}

# A tethered stack's recorded pid is its process group's leader, so one signal
# reaches every process the stack started.
group() { [[ "$(ps -o pgid= -p "$1" | tr -d ' ')" == "$1" ]]; }

# Pids the stubs recorded after the first <n> lines of the record that are still
# running. "After" is a position in the record, never a larger pid: pids wrap,
# and on a loaded machine they wrap within one run, so a pid issued after the
# wrap is smaller than an earlier stack's and that stack, still running, would
# be counted as a survivor. A zombie still answers kill -0, so check the state:
# the tether SIGKILLs a process that ignores SIGTERM, and a killed process is not
# a survivor.
survivors() {
	local p state
	while IFS= read -r p; do
		state="$(ps -o state= -p "$p" 2>/dev/null | tr -d ' ')"
		if [[ -n "${state}" && "${state}" != Z* ]]; then echo "$p"; fi
	done < <(tail -n "+$(($1 + 1))" "${DEV_FIXTURE_PIDS}")
}

# A child that leaves the group outlives the tether; reap and restart stop it.
# Job control gives the background job a process group of its own, the way `op
# run` leads one: the tether's group kill reaches the shell, never this child.
# macOS hides the environment of its own platform binaries (/bin/bash, sleep), so
# the child is a Homebrew bash when there is one; `op`, `aube` and `node` are not
# platform binaries, and their environment shows.
for DEV_FIXTURE_ESCAPEE_SHELL in /opt/homebrew/bin/bash /usr/local/bin/bash "$(command -v bash)"; do
	[[ -x "${DEV_FIXTURE_ESCAPEE_SHELL}" ]] && break
done
export DEV_FIXTURE_ESCAPEE_SHELL
escaping_serve() {
	cat >"$1" <<'SERVE'
#!/usr/bin/env bash
set -euo pipefail
set -m
"${DEV_FIXTURE_ESCAPEE_SHELL}" -c 'while :; do sleep 1; done' &
printf '%s\n' "$!" >>"${DEV_FIXTURE_PIDS}"
wait
SERVE
	chmod +x "$1"
}

gone() {
	local state
	state="$(ps -o state= -p "$1" 2>/dev/null | tr -d ' ')"
	[[ -z "${state}" || "${state}" == Z* ]]
}

newest_pid_is_not() { [[ "$(tail -n 1 "${DEV_FIXTURE_PIDS}")" != "$1" ]]; }

# A worktree of <repo> whose stack has a child in a group of its own; sets leader
# and escapee, and leaves the shell in <repo>.
start_escaping() { # <repo> <worktree dir>
	local floor
	floor="$(tail -n 1 "${DEV_FIXTURE_PIDS}")"
	git -C "$1" worktree add -q -b "feat/${2##*/}" "$2"
	mkdir -p "$2/mise-tasks"
	escaping_serve "$2/mise-tasks/dev-serve"
	cd "$2"
	run_dev dev || fail "dev in $2 must start the escaping stack"
	cd "$1"
	leader="$(sed -n 1p "${cache}/$(basename "$2").pid")"
	wait_for newest_pid_is_not "${floor}" || fail "the escaping child never started in $2"
	escapee="$(tail -n 1 "${DEV_FIXTURE_PIDS}")"
}

# The worktree goes; the tether stops the group, and the escapee is what is left.
remove_escaping() { # <repo> <worktree dir>
	git -C "$1" worktree remove --force "$2"
	git -C "$1" worktree prune
	wait_for gone "${leader}" || fail "the tether must stop the stack's group when $2 goes"
	if gone "${escapee}"; then fail "a child in a group of its own must outlive the tether, or reap has no job"; fi
}
