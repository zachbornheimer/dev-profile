#!/usr/bin/env bash
# The push-time shellcheck check blocks on warnings and errors, not on info or
# style tips: a single-quoted `node -e '...'` script (SC2016, info) must pass,
# an unused variable (SC2034, warning) must fail.
# Usage: shellcheck-severity-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: shellcheck-severity-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL shellcheck-severity fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# The command the profile runs at push, with hk's file placeholder left to fill.
template="$(jq -er '.tools.shellcheck.hooks["pre-push"].check' "${out}/profile.json")" ||
	fail "profile.json has no shellcheck pre-push check"
[[ "${template}" == *"{{files}}"* ]] || fail "check has no {{files}} placeholder: ${template}"

run_check() {
	local command="${template//\{\{files\}\}/$1}"
	(cd "${work}" && bash -c "${command}") >"${work}/output.txt" 2>&1
}

# Only an info-level finding: SC2016, expressions do not expand in single quotes.
cat >"${work}/info-only.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
node -e 'console.log(`${process.env.HOME}`)'
SCRIPT
# Control: the script really does carry the info finding the check must tolerate.
(cd "${work}" && shellcheck --format=gcc info-only.sh) >"${work}/output.txt" 2>&1 || true
grep -Fq "SC2016" "${work}/output.txt" || fail "info-only.sh no longer triggers SC2016, so the case proves nothing"
run_check info-only.sh || fail "an info-level finding (SC2016) must not block a push"

# A true warning: SC2034, a variable that is assigned and never used.
cat >"${work}/warning.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
unused=1
SCRIPT
if run_check warning.sh; then fail "a warning (SC2034) must block a push"; fi
grep -Fq "SC2034" "${work}/output.txt" || fail "the failure must name the warning"

echo "shellcheck-severity fixture ok"
