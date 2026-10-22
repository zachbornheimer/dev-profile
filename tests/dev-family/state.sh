#!/usr/bin/env bash
# The dev family's state machine on a declared serve script: dev:status is a
# read-only probe, dev starts once and prints the URL, dev:start is idempotent,
# concurrent starts leave one stack under the per-checkout lock, dev:restart is
# the only verb that stops, and dev:attach runs in the foreground and writes no
# state. Usage: state.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn='' dev=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
git init -q -b main "${repo}"
cd "${repo}"
mkdir -p mise-tasks
sleeper_serve mise-tasks/dev-serve
git add -A
git commit -qm "declared serve"

# Read-only probe, down: no pidfile, no lockfile.
if run_dev status; then fail "dev:status must exit non-zero when the stack is down"; fi
expect '^state=down$'
[[ ! -e "${cache}/${rn}.pid" && ! -e "${cache}/${rn}.lock" ]] || fail "dev:status must not create a pidfile or a lockfile"

# dev: status, then start, then status -> serving on this checkout's own route.
run_dev || fail "dev must exit 0 when it ends serving"
expect '^state=down$'
expect "^https://${rn}\\.localhost\$"
expect "^state=running url=https://${rn}\\.localhost pid=[0-9]+\$"
expect_spawn_name "${rn}"
expect_spawn 'exec ./mise-tasks/dev-serve'
[[ -f "${cache}/${rn}.log" ]] || fail "the daemon's output must be captured in the log"
wait_spawns 1
[[ "$(spawns)" -eq 1 ]] || fail "dev must start exactly one stack"

# Idempotent: same pid, no second spawn, silent.
pid="$(sed -n 1p "${cache}/${rn}.pid")"
run_dev start || fail "dev:start on a running stack must exit 0"
[[ ! -s "${work}/output.txt" ]] || fail "dev:start on a running stack must be silent"
[[ "$(sed -n 1p "${cache}/${rn}.pid")" == "${pid}" ]] || fail "dev:start must not restart a running stack"
[[ "$(spawns)" -eq 1 ]] || fail "dev:start must not spawn a second stack"

# Concurrent starts from a down state: the lock leaves exactly one stack.
stop_stack "${rn}"
"${dev}" start >"${work}/a.txt" 2>&1 &
pa=$!
"${dev}" start >"${work}/b.txt" 2>&1 &
pb=$!
wait "${pa}" || fail "a concurrent dev:start failed"
wait "${pb}" || fail "a concurrent dev:start failed"
wait_spawns 2
[[ "$(spawns)" -eq 2 ]] || fail "two concurrent dev:start calls must leave one stack, saw $(spawns)"
run_dev status || fail "the stack must be running after a concurrent start"
expect '^state=running'

# restart: the only verb that stops. New pid, one new spawn, same route.
old="$(sed -n 1p "${cache}/${rn}.pid")"
run_dev restart || fail "dev:restart must exit 0"
[[ "$(sed -n 1p "${cache}/${rn}.pid")" != "${old}" ]] || fail "dev:restart must start a new stack"
if kill -0 "${old}" 2>/dev/null; then fail "dev:restart must stop the old stack"; fi
wait_spawns 3
[[ "$(spawns)" -eq 3 ]] || fail "dev:restart must spawn exactly one stack"
expect "^https://${rn}\\.localhost\$"

# attach: foreground, and no state written.
before="$(sed -n 1p "${cache}/${rn}.pid")"
printf '#!/usr/bin/env bash\nset -euo pipefail\necho attach-ran\n' >mise-tasks/dev-serve
chmod +x mise-tasks/dev-serve
run_dev attach || fail "dev:attach must return the command's status"
expect '^attach-ran$'
[[ "$(sed -n 1p "${cache}/${rn}.pid")" == "${before}" ]] || fail "dev:attach must not touch the pidfile"

echo "dev-family state fixture ok"
