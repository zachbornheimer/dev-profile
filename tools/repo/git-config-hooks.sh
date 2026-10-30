#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/git-config-hooks.sh: `mise run generate` copies it into bin/.

# Config-based hooks arrived in 2.54. An older git runs none of them: the global
# gates look installed and never fire, and a push goes unjudged.
version="$(git version | sed -E 's/^git version ([0-9]+\.[0-9]+).*/\1/')"
major="${version%%.*}"
minor="${version#*.}"
if ((major > 2 || (major == 2 && minor >= 54))); then exit 0; fi
# Before `mise install` there is no pinned git to name: that is bootstrap, not drift.
pinned="$(mise which git 2>/dev/null || true)"
if [[ -z "${pinned}" ]]; then
	echo "note: git ${version} predates config-based hooks (2.54); run mise install, then open a new shell" >&2
	exit 0
fi
echo "FAIL: $(command -v git) is git ${version} and runs no config-based hooks; the profile pins ${pinned}, which does, and every global gate is skipped until it resolves first." >&2
exit 1
