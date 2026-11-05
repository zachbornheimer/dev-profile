#!/usr/bin/env bash
# The install retry: a release download that answers 504 is retried instead of
# failing the job, a genuine failure still fails it, and the attempt budget is
# the ceiling. Usage: tools-install-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: tools-install-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
installer="${out}/bin/dev-profile-tools-install"

fail() {
	echo "FAIL tools install fixture: $*" >&2
	exit 1
}

# A mise that fails its first ${FAILS} installs the way a release download
# answering 504 does, then succeeds. ${COUNT} records the installs it saw.
mkdir -p "${work}/bin"
cat >"${work}/bin/mise" <<'SHIM'
#!/usr/bin/env bash
count="$(cat "${COUNT}" 2>/dev/null || echo 0)"
count=$((count + 1))
printf '%s\n' "${count}" >"${COUNT}"
if ((count <= ${FAILS:-0})); then
	echo 'mise ✗ aqua:example/tool@1.0.0  25.0s · failed: HTTP status server error (504 Gateway Timeout)' >&2
	echo 'mise ERROR installation failed; previous lockfiles were preserved' >&2
	exit 1
fi
echo 'mise install: installed'
SHIM
chmod +x "${work}/bin/mise"
# No delay: the retry's wait is not what this fixture measures.
export PATH="${work}/bin:${PATH}" DEV_PROFILE_TOOLS_INSTALL_DELAY_SECONDS=0

# One flaky fetch: the retry swallows it and the install still succeeds.
if ! FAILS=1 COUNT="${work}/once" bash "${installer}" >"${work}/once.txt" 2>&1; then
	sed 's/^/  | /' "${work}/once.txt" >&2
	fail "a single 504 must not fail the install"
fi
[[ "$(cat "${work}/once")" == 2 ]] || fail "want 2 install attempts after one 504, got $(cat "${work}/once")"
grep -Fq 'retrying in 0s' "${work}/once.txt" || fail "the retry was not reported"

# A failure that outlasts the retries still fails the job, after the budget.
if FAILS=99 COUNT="${work}/always" bash "${installer}" >"${work}/always.txt" 2>&1; then
	fail "an install that never succeeds must fail"
fi
[[ "$(cat "${work}/always")" == 5 ]] || fail "want the default budget of 5 attempts, got $(cat "${work}/always")"
if FAILS=99 DEV_PROFILE_TOOLS_INSTALL_ATTEMPTS=2 COUNT="${work}/two" bash "${installer}" >/dev/null 2>&1; then
	fail "a custom budget of 2 attempts must fail"
fi
[[ "$(cat "${work}/two")" == 2 ]] || fail "want 2 attempts, got $(cat "${work}/two")"

echo "tools install fixture ok"
