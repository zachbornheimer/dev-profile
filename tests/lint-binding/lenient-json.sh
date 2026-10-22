#!/usr/bin/env bash
# `profile:lint` through a runner and the local entry must reach the strict-json
# step: a trailing comma in a .json file passes dprint's lenient JSON plugin and
# fails only there. Usage: lenient-json.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work=''
. "$(dirname "$0")/world.sh" "$@"

# dprint's JSON plugin accepts a trailing comma; only the strict-json step rejects it,
# so this fails only if that step is reachable under the lint profile.
lenient_json="$(new_repo lenient-json)"
printf '{"a": 1,}\n' >"${lenient_json}/data.json"
for context in runner entry; do
	if lint "${context}" "${lenient_json}"; then fail "${context}: a trailing comma in .json must fail profile:lint"; fi
	grep -q 'not strict JSON' "${work}/output.txt" || fail "${context}: the strict-json step must report data.json"
done

echo "lint-binding lenient-json fixture ok"
