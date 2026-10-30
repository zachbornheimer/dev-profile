#!/usr/bin/env bash
set -euo pipefail
# Edit lib/commit-msg.sh: `mise run generate` copies it into bin/ as dev-profile-commit-msg.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"
# commit-msg hook: the subject must be a Conventional Commit.
file="${1:?usage: dev-profile-commit-msg <message-file>}"
subject="$(sed -n '/^#/d; /./{p;q;}' "${file}")"
case "${subject}" in
"Merge "* | "Revert "* | "fixup! "* | "squash! "* | "amend! "*) exit 0 ;;
esac
types="${PROFILE_COMMIT_TYPES:?}"
pattern="^(${types// /|})([(][^)]+[)])?!?: .+"
if [[ "${subject}" =~ ${pattern} ]]; then
	exit 0
fi
echo "commit-msg: subject must be 'type(scope): description'." >&2
echo "  types: ${types// /, }" >&2
echo "  got:   ${subject}" >&2
exit 1
