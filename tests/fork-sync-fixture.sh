#!/usr/bin/env bash
# dev-profile-fork-sync: after the builds, `fork doctor` is a gate. A finding is
# printed and exits 3; a mirror that could not fast-forward still exits 1; a clean
# doctor exits 0. bun and gh are stubs. Usage: fork-sync-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: fork-sync-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
sync="${out}/bin/dev-profile-fork-sync"

fail() {
	echo "FAIL fork sync fixture: $*" >&2
	exit 1
}

mkdir -p "${work}/bin" "${work}/home/.omp/agent/tools/fork"
cat >"${work}/bin/bun" <<'SHIM'
#!/usr/bin/env bash
case "$1" in
*/cli.ts)
	case "$2" in
	sync) printf '%s\n' "${SYNC_OUT}" ;;
	status) printf '%s\n' "${STATUS_OUT}" ;;
	doctor) printf '%s\n' "${DOCTOR_OUT}" ;;
	*) echo "unexpected bun cli op $2" >&2; exit 1 ;;
	esac
	;;
*/report.ts) printf '%s\n' 'repo mirror' ;;
*) echo "unexpected bun $1" >&2; exit 1 ;;
esac
SHIM
cat >"${work}/bin/gh" <<'SHIM'
#!/usr/bin/env bash
exit 0
SHIM
chmod +x "${work}/bin/bun" "${work}/bin/gh"
touch "${work}/home/.omp/agent/tools/fork/cli.ts" "${work}/home/.omp/agent/tools/fork/report.ts"

export FORK_SYNC_PATH="${work}/bin" HOME="${work}/home"
export SYNC_OUT='[{"repo":"hexyl","action":"none"}]'
export STATUS_OUT='[{"repo":"hexyl","managed":true}]'
export DOCTOR_OUT='[{"repo":"hexyl","findings":[]}]'

run() { # <name>: runs the sync and records its exit, never failing the fixture
	set +e
	bash "${sync}" >"${work}/$1.out" 2>"${work}/$1.err"
	printf '%s\n' "$?" >"${work}/$1.exit"
	set -e
}

run clean
[[ "$(cat "${work}/clean.exit")" == 0 ]] || fail "a current mirror and a clean doctor must exit 0, got $(cat "${work}/clean.exit")"
grep -Fq 'fork sync: started hexyl build' "${work}/clean.out" "${work}/clean.err" || fail "the build must be dispatched before the doctor gate"

export SYNC_OUT='[{"repo":"hexyl","action":"refuse","detail":"ahead"}]'
run refused
[[ "$(cat "${work}/refused.exit")" == 1 ]] || fail "a mirror that could not fast-forward must exit 1, got $(cat "${work}/refused.exit")"
grep -Fq 'some mirrors did not fast-forward' "${work}/refused.err" || fail "the refusal must be reported"

export SYNC_OUT='[{"repo":"hexyl","action":"none"}]'
export DOCTOR_OUT='[{"repo":"hexyl","findings":[{"check":"hook","detail":"the mirror hook is missing or stale; run `fork hooks`"}]}]'
run finding
[[ "$(cat "${work}/finding.exit")" == 3 ]] || fail "a doctor finding must exit 3, got $(cat "${work}/finding.exit")"
grep -Fq 'fork sync: hexyl hook: the mirror hook is missing or stale; run `fork hooks`' "${work}/finding.err" || fail "the finding must be printed"
grep -Fq 'fork sync: started hexyl build' "${work}/finding.out" "${work}/finding.err" || fail "a finding must not skip the build dispatch"

echo "fork sync fixture ok"
