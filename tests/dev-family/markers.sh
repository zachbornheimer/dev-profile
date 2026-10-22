#!/usr/bin/env bash
# The dev family's marker inference: a repo with nothing to serve is
# unconfigured (exit 1, one clear line, no state), and with no declared serve
# script composer.json, a package.json dev script, or both decide the command.
# Usage: markers.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn=''
. "$(dirname "$0")/world.sh" "$@"

# --- nothing to serve: unconfigured, exit 1, one clear line, no state

none="${work}/${rn}-none"
git init -q -b main "${none}"
cd "${none}"

if run_dev status; then fail "dev:status on an unconfigured repo must exit 1"; fi
expect '^state=unconfigured$'
if run_dev; then fail "dev on an unconfigured repo must exit 1"; fi
expect 'nothing to serve here'
[[ "$(lines "${work}/output.txt")" -eq 1 ]] || fail "dev must print one clear line for an unconfigured repo"
[[ ! -e "${cache}/${rn}-none.pid" && ! -e "${cache}/${rn}-none.lock" ]] || fail "an unconfigured probe must not create state"

# --- marker inference, with no declared script

repo="${work}/${rn}"
git init -q -b main "${repo}"
cd "${repo}"
printf '{"require":{}}\n' >composer.json
git add -A
git commit -qm composer
run_dev start || fail "dev:start must infer a serve command from composer.json"
# The inferred command keeps the port a literal `$PORT` for the child shell
# (portless assigns it per checkout), so the assertion quotes it escaped.
expect_spawn "php artisan serve --port=\$PORT"

stop_stack "${rn}"
rm composer.json
printf '{"scripts":{"dev":"vite"}}\n' >package.json
git add -A
git commit -qm node
run_dev start || fail "dev:start must infer a serve command from a package.json dev script"
expect_spawn "aube run dev -- --port \$PORT"

stop_stack "${rn}"
printf '{"require":{}}\n' >composer.json
git add -A
git commit -qm pair
run_dev start || fail "dev:start must run the php and js pair together"
expect_spawn "php artisan serve --port=\$PORT & exec aube run dev"

echo "dev-family markers fixture ok"
