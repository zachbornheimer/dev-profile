# shellcheck shell=bash
# Sourced by lib/adapters/<id>.sh, a contract adapter (`dev-profile-contract-<id>
# <verb>`): exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
# Edit lib/sh/contract-adapter.sh: `mise run generate` copies it into lib/.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/facts.sh"
failed=0

# Run one tool; record a failure and keep going so every check reports.
step() {
	echo "+ $*" >&2
	"$@" || failed=1
}

nothing_to_do() {
	exit "${PROFILE_CONTRACT_NOTHING_TO_DO:?}"
}

# The adapter's exit: 1 when any step failed.
finish() {
	exit "${failed}"
}
