#!/usr/bin/env bash
# `profile:lint` through a runner and the local entry: a clean repo passes, invalid
# JSON fails and names its file, and with the rendered PATH binding stripped a
# clean repo fails, so the passes are the binding's and not the environment's.
# Usage: json.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
out='' work=''
. "$(dirname "$0")/world.sh" "$@"

clean="$(new_repo clean)"
printf '{\n  "a": 1\n}\n' >"${clean}/data.json"
bad_json="$(new_repo bad-json)"
printf '{"a": }\n' >"${bad_json}/data.json"

# Red control: with the PATH binding stripped from the rendered config the contract
# scripts are not found, so a clean repo must fail; the runs below pass only through it.
mkdir -p "${work}/stripped/conf.d"
grep -v '^path = ' "${out}/mise-profile.toml" >"${work}/stripped/conf.d/dev-profile.toml"
if (cd "${clean}" && MISE_CONFIG_DIR="${work}/stripped" mise run profile:lint) >"${work}/output.txt" 2>&1; then
	fail "runner: a clean repo passed profile:lint with the PATH binding stripped"
fi

for context in runner entry; do
	lint "${context}" "${clean}" || fail "${context}: a clean repo must pass profile:lint"
	if lint "${context}" "${bad_json}"; then fail "${context}: invalid JSON must fail profile:lint"; fi
	grep -q 'data.json' "${work}/output.txt" || fail "${context}: the failure must name data.json"
done

echo "lint-binding json fixture ok"
