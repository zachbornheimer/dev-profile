#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/identity-guard.sh: `mise run generate` copies it into bin/.

# Source of the rule: agentmux cmd/identityguard (ZYS-1067). A local identity
# or an unsigned-commit override makes this repo commit differently from every
# other one, so the push fails and names the key to unset.
rejected=0
reject() { # <what is set> <key to unset> <what global config owns>
	echo "identity-guard: local git config sets $1; run: git config --local --unset $2 ($3 comes from global config)" >&2
	rejected=1
}
for key in user.name user.email; do
	[[ -z "$(git config --local --get "${key}" || true)" ]] || reject "${key}" "${key}" identity
done
[[ "$(git config --local --get commit.gpgsign || true)" != "false" ]] ||
	reject "commit.gpgsign=false" "commit.gpgsign" signing
exit "${rejected}"
