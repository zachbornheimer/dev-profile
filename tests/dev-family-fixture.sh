#!/usr/bin/env bash
# The dev task family against real git and a stubbed portless: the state machine
# (dev, dev:status, dev:start, dev:restart, dev:attach), the per-checkout lock,
# pidfile and route name, and the marker inference. `portless`, `php` and `aube`
# are stubs, so no proxy, php, node or network is needed; the portless stub
# records every spawn, which is how the fixture proves one stack.
# Usage: dev-family-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: dev-family-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
dev="${out}/bin/dev-profile-dev"
cache="${work}/cache/dev-profile/dev"

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
export DEV_FIXTURE_SPAWNS="${work}/spawns" DEV_FIXTURE_PIDS="${work}/pids"
: >"${DEV_FIXTURE_SPAWNS}"
: >"${DEV_FIXTURE_PIDS}"
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

spawns() { awk 'END { print NR }' "${DEV_FIXTURE_SPAWNS}"; }

expect() { grep -qE "$1" "${work}/output.txt" || fail "the output must match /$1/"; }

expect_spawn() { grep -qF "$1" "${DEV_FIXTURE_SPAWNS}" || fail "no spawn ran '$1'"; }

expect_spawn_name() { cut -f1 "${DEV_FIXTURE_SPAWNS}" | grep -qxF "$1" || fail "no spawn for route '$1'"; }

lines() { awk 'END { print NR }' "$1"; }

# dev:restart is the only verb that stops, so when the fixture needs a down
# stack it signals the recorded pid itself.
stop_stack() {
	if [[ -f "${cache}/$1.pid" ]]; then
		kill -TERM "$(sed -n 1p "${cache}/$1.pid")" 2>/dev/null || :
		rm -f "${cache}/$1.pid"
	fi
}

# --- nothing to serve: unconfigured, exit 1, one clear line, no state

bare="${work}/bare"
git init -q -b main "${bare}"
cd "${bare}"

if run_dev status; then fail "dev:status on an unconfigured repo must exit 1"; fi
expect '^state=unconfigured$'
if run_dev; then fail "dev on an unconfigured repo must exit 1"; fi
expect 'nothing to serve here'
[[ "$(lines "${work}/output.txt")" -eq 1 ]] || fail "dev must print one clear line for an unconfigured repo"
[[ ! -e "${cache}/bare.pid" && ! -e "${cache}/bare.lock" ]] || fail "an unconfigured probe must not create state"

# --- a declared serve script: the state machine

repo="${work}/repo"
git init -q -b main "${repo}"
cd "${repo}"
mkdir -p mise-tasks
sleeper_serve mise-tasks/dev-serve
git add -A
git commit -qm "declared serve"

# Read-only probe, down: no pidfile, no lockfile.
if run_dev status; then fail "dev:status must exit non-zero when the stack is down"; fi
expect '^state=down$'
[[ ! -e "${cache}/repo.pid" && ! -e "${cache}/repo.lock" ]] || fail "dev:status must not create a pidfile or a lockfile"

# dev: status, then start, then status -> serving on this checkout's own route.
run_dev || fail "dev must exit 0 when it ends serving"
expect '^state=down$'
expect '^https://repo\.localhost$'
expect '^state=running url=https://repo\.localhost pid=[0-9]+$'
expect_spawn_name repo
expect_spawn 'exec ./mise-tasks/dev-serve'
[[ -f "${cache}/repo.log" ]] || fail "the daemon's output must be captured in the log"
[[ "$(spawns)" -eq 1 ]] || fail "dev must start exactly one stack"

# Idempotent: same pid, no second spawn, silent.
pid="$(sed -n 1p "${cache}/repo.pid")"
run_dev start || fail "dev:start on a running stack must exit 0"
[[ ! -s "${work}/output.txt" ]] || fail "dev:start on a running stack must be silent"
[[ "$(sed -n 1p "${cache}/repo.pid")" == "${pid}" ]] || fail "dev:start must not restart a running stack"
[[ "$(spawns)" -eq 1 ]] || fail "dev:start must not spawn a second stack"

# Concurrent starts from a down state: the lock leaves exactly one stack.
stop_stack repo
"${dev}" start >"${work}/a.txt" 2>&1 &
pa=$!
"${dev}" start >"${work}/b.txt" 2>&1 &
pb=$!
wait "${pa}" || fail "a concurrent dev:start failed"
wait "${pb}" || fail "a concurrent dev:start failed"
[[ "$(spawns)" -eq 2 ]] || fail "two concurrent dev:start calls must leave one stack, saw $(spawns)"
run_dev status || fail "the stack must be running after a concurrent start"
expect '^state=running'

# restart: the only verb that stops. New pid, one new spawn, same route.
old="$(sed -n 1p "${cache}/repo.pid")"
run_dev restart || fail "dev:restart must exit 0"
[[ "$(sed -n 1p "${cache}/repo.pid")" != "${old}" ]] || fail "dev:restart must start a new stack"
if kill -0 "${old}" 2>/dev/null; then fail "dev:restart must stop the old stack"; fi
[[ "$(spawns)" -eq 3 ]] || fail "dev:restart must spawn exactly one stack"
expect '^https://repo\.localhost$'

# attach: foreground, and no state written.
before="$(sed -n 1p "${cache}/repo.pid")"
printf '#!/usr/bin/env bash\nset -euo pipefail\necho attach-ran\n' >mise-tasks/dev-serve
chmod +x mise-tasks/dev-serve
run_dev attach || fail "dev:attach must return the command's status"
expect '^attach-ran$'
[[ "$(sed -n 1p "${cache}/repo.pid")" == "${before}" ]] || fail "dev:attach must not touch the pidfile"

# --- marker inference, with no declared script

stop_stack repo
rm -f mise-tasks/dev-serve
rmdir mise-tasks
printf '{"require":{}}\n' >composer.json
git add -A
git commit -qm composer
run_dev start || fail "dev:start must infer a serve command from composer.json"
# The inferred command keeps the port a literal `$PORT` for the child shell
# (portless assigns it per checkout), so the assertion quotes it escaped.
expect_spawn "php artisan serve --port=\$PORT"

stop_stack repo
rm composer.json
printf '{"scripts":{"dev":"vite"}}\n' >package.json
git add -A
git commit -qm node
run_dev start || fail "dev:start must infer a serve command from a package.json dev script"
expect_spawn "aube run dev -- --port \$PORT"

stop_stack repo
printf '{"require":{}}\n' >composer.json
git add -A
git commit -qm pair
run_dev start || fail "dev:start must run the php and js pair together"
expect_spawn "php artisan serve --port=\$PORT & exec aube run dev"

# --- a linked worktree claims <branch>.<repo>.localhost, under the tether

# A tethered stack's recorded pid is its process group's leader, so one signal
# reaches every process the stack started.
group() { [[ "$(ps -o pgid= -p "$1" | tr -d ' ')" == "$1" ]]; }

# Pids recorded after the worktree's stack began that are still running. A
# zombie still answers kill -0, so check the state: the tether SIGKILLs a
# process that ignores SIGTERM, and a killed process is not a survivor.
survivors() {
	local p state
	while IFS= read -r p; do
		state="$(ps -o state= -p "$p" 2>/dev/null | tr -d ' ')"
		if [[ "$p" -gt "$1" && -n "${state}" && "${state}" != Z* ]]; then echo "$p"; fi
	done <"${DEV_FIXTURE_PIDS}"
}

wt="${work}/repo-feat-x"
git worktree add -q -b feat/x "${wt}"
cd "${wt}"
run_dev || fail "dev in a worktree must work"
expect '^state=running url=https://feat-x\.repo\.localhost pid=[0-9]+$'
expect_spawn_name feat-x.repo
[[ "$(sed -n 3p "${cache}/repo-feat-x.pid")" == feat-x.repo ]] ||
	fail "a branch worktree must record <branch>.<repo> as its route"
leader="$(sed -n 1p "${cache}/repo-feat-x.pid")"
group "${leader}" || fail "the tether must record a stack's process-group leader"

# restart goes through the same spawn path: a fresh group, still one leader, and
# the group it replaced is gone.
old="${leader}"
run_dev restart || fail "dev:restart in a worktree must work"
leader="$(sed -n 1p "${cache}/repo-feat-x.pid")"
[[ "${leader}" != "${old}" ]] || fail "dev:restart must start a new stack"
group "${leader}" || fail "dev:restart must tether the new stack too"
if kill -0 "${old}" 2>/dev/null; then fail "dev:restart must stop the old group"; fi

# Removing the worktree reaps the restarted tree, not just the first one. The
# tether's watcher polls, so allow a generous window before judging it.
floor="$(tail -n 1 "${DEV_FIXTURE_PIDS}")"
cd "${repo}"
sleep 1
git worktree remove --force "${wt}"
git worktree prune
waited=0
while [[ -n "$(survivors "${floor}")" && "${waited}" -lt 20 ]]; do
	sleep 1
	waited=$((waited + 1))
done
[[ -z "$(survivors "${floor}")" ]] ||
	fail "removing the worktree must reap the tethered stack; survivors: $(survivors "${floor}")"

# --- every worktree gets its own host, whatever its branch

# portless's own prefix would give feat/x and fix/x the same host (x), and none
# at all to a detached HEAD or a master branch. The script names the host itself,
# so all of these stay apart from each other and from the main checkout.
expect_worktree_route() { # <dir> <branch args...> -- <expected route>
	local dir="$1" route="${*: -1}" args=("${@:2:$#-2}")
	git worktree add -q "${args[@]}" "${dir}"
	cd "${dir}"
	run_dev || fail "dev in worktree ${dir} must work"
	expect "^state=running url=https://${route//./\\.}\\.localhost pid=[0-9]+"
	[[ "$(sed -n 3p "${cache}/$(basename "${dir}").pid")" == "${route}" ]] ||
		fail "worktree ${dir} must record ${route} as its route"
	cd "${repo}"
}
expect_worktree_route "${work}/repo-feat-x" -B feat/x feat-x.repo
expect_worktree_route "${work}/repo-fix-x" -B fix/x fix-x.repo
expect_worktree_route "${work}/repo-detached" --detach detached.repo
expect_worktree_route "${work}/repo-master" -B master master.repo
# Four stacks at once on four different hosts.
[[ "$(cut -f1 "${DEV_FIXTURE_SPAWNS}" | sort -u | grep -cE '^(feat-x|fix-x|detached|master)\.repo$')" == 4 ]] ||
	fail "each worktree must register its own host"
for name in repo-feat-x repo-fix-x repo-detached repo-master; do
	stop_stack "${name}"
	git worktree remove --force "${work}/${name}"
done
git worktree prune

# A branch name too long for a DNS label keeps a 63-character host label.
long="feat/$(printf 'a%.0s' {1..80})"
git worktree add -q -b "${long}" "${work}/repo-long"
cd "${work}/repo-long"
run_dev || fail "dev in a long-branch worktree must work"
label="$(sed -n 3p "${cache}/repo-long.pid" | cut -d. -f1)"
((${#label} <= 63)) || fail "a worktree host label must fit in 63 characters, got ${#label}"
stop_stack repo-long
cd "${repo}"
git worktree remove --force "${work}/repo-long"
git worktree prune

# A bare clone named <repo>.git names its repo without the suffix.
git clone -q --bare "${repo}" "${work}/bare-home/myrepo.git"
git -C "${work}/bare-home/myrepo.git" worktree add -q -b feat/b "${work}/myrepo-feat-b" main
cd "${work}/myrepo-feat-b"
mkdir -p mise-tasks
sleeper_serve mise-tasks/dev-serve
run_dev || fail "dev in a bare repo's worktree must work"
expect '^state=running url=https://feat-b\.myrepo\.localhost pid=[0-9]+$'
stop_stack myrepo-feat-b
cd "${repo}"

# --- worktrunk unusable: the plain detached spawn, signalled as one process

cat >"${work}/bin/wt" <<'STUB'
#!/usr/bin/env bash
exit 127
STUB
chmod +x "${work}/bin/wt"
run_dev restart || fail "dev:restart must work without a usable worktrunk"
[[ "$(sed -n 2p "${cache}/repo.pid")" == spawn ]] ||
	fail "without a usable worktrunk the stack must be a plain detached spawn"
expect '^https://repo\.localhost$'
rm -f "${work}/bin/wt"

echo "dev-family fixture ok"
