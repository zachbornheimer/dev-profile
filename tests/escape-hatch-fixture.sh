#!/usr/bin/env bash
# The README's dprint escape hatch must resolve on any machine: its `extends`
# is home-relative and names the profile's default render path, with no
# user-specific absolute path. dprint is run with a scratch HOME.
# Usage: escape-hatch-fixture.sh <readme>
set -euo pipefail

readme="${1:?usage: escape-hatch-fixture.sh <readme>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL escape-hatch fixture: $*" >&2
	exit 1
}

# The hatch is the first jsonc block that sets "extends".
extends="$(awk '/^```jsonc/{in_block=1; next} /^```/{in_block=0} in_block' "${readme}" |
	sed -En 's/^[[:space:]]*"extends": "([^"]+)".*/\1/p' | head -n 1)"
[[ -n "${extends}" ]] || fail "no \"extends\" in a jsonc block of ${readme}"
[[ "${extends}" == "~/"* ]] || fail "extends must start with ~/, not a machine path: ${extends}"

dprint_bin="$(mise which dprint)"
profile_config="${work}/home/${extends#\~/}"
mkdir -p "${work}/repo" "$(dirname "${profile_config}")"
echo '{}' >"${profile_config}"
printf '{\n  "extends": "%s",\n  "excludes": ["schemas/"]\n}\n' "${extends}" >"${work}/repo/dprint.jsonc"

(cd "${work}/repo" && HOME="${work}/home" "${dprint_bin}" output-resolved-config >/dev/null 2>&1) ||
	fail "extends ${extends} must resolve under a scratch HOME"
rm "${profile_config}"
(cd "${work}/repo" && HOME="${work}/home" "${dprint_bin}" output-resolved-config >/dev/null 2>&1) &&
	fail "extends must fail where the profile is not rendered, or the test proves nothing"

echo "escape-hatch fixture ok"
