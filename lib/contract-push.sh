#!/usr/bin/env bash
set -euo pipefail
# Edit lib/contract-push.sh: `mise run generate` copies it into bin/ as dev-profile-contract-push.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"

# git exports GIT_DIR, GIT_INDEX_FILE, … to hooks; clear them so tests that
# create their own throwaway repos do not act on the repo being pushed.
while IFS= read -r var; do unset "${var}"; done < <(git rev-parse --local-env-vars)
# Run the push-time contract verbs. A repo outside a profile code root has no
# contract tasks; say so instead of failing every push there.
if ! mise tasks info "${PROFILE_TASK_NAMESPACE:?}:test" >/dev/null 2>&1; then
	echo "contract: no profile tasks here (not under a profile code root); skipped" >&2
	exit 0
fi
read -ra verbs <<<"${PROFILE_PUSH_VERBS:?}"
failed=()
for verb in "${verbs[@]}"; do
	mise run "${verb}" || failed+=("${verb}")
done
if [[ "${#failed[@]}" -gt 0 ]]; then
	echo "pre-push contract failed: ${failed[*]}" >&2
	exit 1
fi
