#!/usr/bin/env bash
# Extract Claude session id via AOE hook bin. No-op if AOE is unset.
set -eu
IID=$(printenv AOE_INSTANCE_ID 2>/dev/null || true)
[ -n "${IID}" ] || exit 0
HBIN=$(printenv AOE_HOOK_BIN 2>/dev/null || true)
[ -n "${HBIN}" ] || exit 0
[ -x "${HBIN}" ] || exit 0
"${HBIN}" __extract-session-id --field session-id --agent claude 2>/dev/null || true
exit 0
