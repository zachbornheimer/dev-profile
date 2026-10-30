#!/usr/bin/env bash
set -uo pipefail
# Edit lib/ci.sh: `mise run generate` copies it into bin/ as dev-profile-ci.
# A bin script, not an inline task `run`: mise renders task scripts through Tera,
# which reads the `#` of bash's array-length expansion as a comment opener.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"
# Run every ci verb (repo overrides included), then fail if any failed.
read -ra verbs <<<"${PROFILE_CI_VERBS:?}"
failed=()
for verb in "${verbs[@]}"; do
	mise run "${verb}" || failed+=("${verb}")
done
if [[ "${#failed[@]}" -gt 0 ]]; then
	echo "ci failed: ${failed[*]}" >&2
	exit 1
fi
echo "ci ok"
