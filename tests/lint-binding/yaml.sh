#!/usr/bin/env bash
# `profile:lint` on YAML through a runner and the local entry: the generated
# yamllint policy accepts a SHA-pinned action, rejects duplicate keys, and with
# its binding stripped yamllint's defaults apply instead.
# Usage: yaml.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
out='' work=''
. "$(dirname "$0")/world.sh" "$@"

# A SHA-pinned action exceeds yamllint's default 80-column limit. The profile's
# generated policy permits it and does not require a YAML document marker.
clean_yaml="$(new_repo clean-yaml)"
printf '%s\n' 'action: zachbornheimer/dev-profile@6376251df9c4df0b7063464303b5de1b833fabad # immutable action revision' >"${clean_yaml}/data.yaml"
for context in runner entry; do
	lint "${context}" "${clean_yaml}" || fail "${context}: valid YAML must use the generated yamllint policy"
done

# Red control: without the binding, hk sees yamllint's defaults instead of the
# rendered policy.
mkdir -p "${work}/yaml-unbound/conf.d"
grep -v '^YAMLLINT_CONFIG_FILE = ' "${out}/mise-profile.toml" >"${work}/yaml-unbound/conf.d/dev-profile.toml"
if (cd "${clean_yaml}" && MISE_CONFIG_DIR="${work}/yaml-unbound" mise run profile:lint) >"${work}/output.txt" 2>&1; then
	fail "runner: valid YAML passed with the yamllint binding stripped"
fi
grep -q 'line-length' "${work}/output.txt" || fail "runner: the unbound control must fail yamllint's default line-length rule"

# Binding the shared policy still rejects YAML defects.
bad_yaml="$(new_repo bad-yaml)"
printf 'key: one\nkey: two\n' >"${bad_yaml}/data.yaml"
for context in runner entry; do
	if lint "${context}" "${bad_yaml}"; then fail "${context}: duplicate YAML keys must fail profile:lint"; fi
	grep -q 'key-duplicates' "${work}/output.txt" || fail "${context}: yamllint must report duplicate keys"
done

echo "lint-binding yaml fixture ok"
