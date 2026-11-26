#!/usr/bin/env bash
# omp's review_pr runs two programs, `ocr` (OpenCodeReview) and `semgrep`, and a Relay
# ticket with a pull request is held until both report complete. The profile is what
# `mise bootstrap` installs on a fresh Linux box, so it has to pin both: on 2026-11-25
# neither was declared for Linux, and every Relay guest answered "ocr: Executable not
# found in $PATH" or "No version is set for shim: semgrep".
# Checks the pins on every OS and, on Linux, that each program starts.
# Usage: review-tools-fixture.sh <checkout>
set -euo pipefail

root="$(cd "${1:?usage: review-tools-fixture.sh <checkout>}" && pwd -P)"
fail() {
	echo "FAIL review tools fixture: $*" >&2
	exit 1
}

# The profile's own pins, whatever this machine's global config adds on top.
export MISE_GLOBAL_CONFIG_FILE="${root}/profile/mise.toml"
cd "${root}"

profile_version() { # backend name; prints the version the profile requests, nothing when it requests none
	mise tool "$1" --json | jq -r '.requested_versions // [] | join(" ")'
}
for pin in github:alibaba/open-code-review pypi:semgrep; do
	version="$(profile_version "${pin}")" || fail "mise could not read the profile's ${pin} declaration"
	[[ -n "${version}" ]] || fail "${pin} is not pinned in languages/*/tools.toml, so a fresh Linux box has no such reviewer"
	[[ "${version}" != latest ]] || fail "${pin} is pinned to latest; one release lookup that times out fails mise bootstrap"
done

# The same probe review_pr makes before it reviews, from the same PATH. Linux only:
# the ocr pin is Linux-only because macOS takes ocr from Homebrew.
if [[ "$(uname -s)" == Linux ]]; then
	for program in ocr semgrep; do
		command -v "${program}" >/dev/null || fail "${program} is not on PATH; run mise install"
		"${program}" --version >/dev/null 2>&1 || fail "${program} --version did not exit 0"
	done
fi

echo "review tools fixture ok"
