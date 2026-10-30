#!/usr/bin/env bash
set -euo pipefail
# Edit lib/git-hook.sh: `mise run generate` copies it into bin/.
# Run one git hook through the active hk config (~/.config/hk).
# A config that does not define the hook, such as a profile not yet updated
# to a newer hook set, skips it instead of failing every commit.
hook="${1:?usage: dev-profile-git-hook <hook> [hk args…]}"
shift
code=0
hk run "${hook}" "$@" || code=$?
[[ "${code}" -ne 0 ]] || exit 0
# Only after a failure: ask hk whether the hook exists at all.
probe="$(hk run "${hook}" --plan "$@" </dev/null 2>&1 || true)"
if [[ "${probe}" == *"Hook '${hook}' not found"* ]]; then
	echo "${hook}: skipped; the hk config in ${XDG_CONFIG_HOME:-${HOME}/.config}/hk does not define it. Update that profile: mise bootstrap --from <profile repo> --update" >&2
	exit 0
fi
exit "${code}"
