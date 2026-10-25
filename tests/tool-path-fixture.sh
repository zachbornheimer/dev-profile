#!/usr/bin/env bash
# Inherited system tools must not shadow profile pins in noninteractive children.
set -euo pipefail

out="${1:?usage: tool-path-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
mkdir -p "${work}/shadow"
printf '#!/bin/sh\nexit 73\n' >"${work}/shadow/git"
chmod +x "${work}/shadow/git"

(
	cd "${work}"
	PATH="${work}/shadow:${PATH}" "${out}/bin/dev-profile-env" \
		--config-dir "${work}/config" -- mise exec -- \
		bash --noprofile --norc -s <<'CHECK'
set -euo pipefail
expected="$(mise which git)"
actual="$(command -v git)"
[[ "$actual" == "$expected" ]] || {
	echo "FAIL tool-path fixture: resolved $actual, expected $expected" >&2
	exit 1
}
git --version
CHECK
)
echo "tool-path fixture ok"
