#!/usr/bin/env bash
# dev:restart on stacks the tether does not own: with worktrunk unusable the
# stack is a plain detached spawn, signalled as one process; and a route held by
# a stack this checkout did not record is stopped by the pid portless reports for
# that route, never an unrelated route's.
# Usage: restart.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
pair_repo "${repo}"
cd "${repo}"
run_dev start || fail "dev:start must start the stack"

# --- worktrunk unusable: the plain detached spawn, signalled as one process

cat >"${work}/bin/wt" <<'STUB'
#!/usr/bin/env bash
exit 127
STUB
chmod +x "${work}/bin/wt"
run_dev restart || fail "dev:restart must work without a usable worktrunk"
[[ "$(sed -n 2p "${cache}/${rn}.pid")" == spawn ]] ||
	fail "without a usable worktrunk the stack must be a plain detached spawn"
expect "^https://${rn}\\.localhost\$"
rm -f "${work}/bin/wt"

# --- a route held by a stack this checkout did not record
#
# A stack started outside the family registers its route with portless but has
# no pidfile. Restart must stop only the PID portless reports for this route.

sleep 300 &
foreign=$!
sleep 300 &
unrelated=$!
printf '%s\n%s\n' "${foreign}" "${unrelated}" >>"${DEV_FIXTURE_PIDS}"
printf '  https://%s.localhost  ->  localhost:4611  (pid %s)\n  https://other.localhost  ->  localhost:4622  (pid %s)\n' "${rn}" "${foreign}" "${unrelated}" >"${DEV_FIXTURE_ROUTES}"
run_dev restart || fail "dev:restart must stop a foreign route holder and start"
if kill -0 "${foreign}" 2>/dev/null; then fail "dev:restart must stop the foreign route holder"; fi
if ! kill -0 "${unrelated}" 2>/dev/null; then fail "dev:restart must not touch the unrelated route holder"; fi
expect '^dev:restart: stopping the route holder'
expect "^https://${rn}[.]localhost\$"
kill -TERM "${unrelated}" 2>/dev/null || :
wait "${unrelated}" 2>/dev/null || :
: >"${DEV_FIXTURE_ROUTES}"

echo "dev-family restart fixture ok"
