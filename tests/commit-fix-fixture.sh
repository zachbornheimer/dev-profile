#!/usr/bin/env bash
# `wt step commit --fix` strips the flag, and a failed commit tells the user
# in zsh and hands the errors to omp. A commit without --fix never does.
set -euo pipefail

out="${1:?usage: commit-fix-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL commit-fix fixture: $*" >&2
	exit 1
}

mkdir -p "${work}/bin"
cat >"${work}/bin/wt" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >>"${FAKE_WT_LOG}"
exit "${FAKE_WT_STATUS:-0}"
EOF
cat >"${work}/bin/omp" <<'EOF'
#!/bin/bash
printf '%s\n' "$1" >>"${FAKE_OMP_LOG}"
printf '%s\n' "$2" >>"${FAKE_OMP_LOG}"
exit 0
EOF
chmod +x "${work}/bin/wt" "${work}/bin/omp"
saved_path=$PATH
export PATH="${work}/bin:${saved_path}"
export FAKE_WT_LOG="${work}/wt.log"
export FAKE_OMP_LOG="${work}/omp.log"

task='We were unable to run wt step commit due to errors. please fix, and then commit with wt step commit.'
notice="wt step commit failed. Running: omp @task '${task}'"

reset_logs() {
	: >"${FAKE_WT_LOG}"
	: >"${FAKE_OMP_LOG}"
}

run_wt() {
	reset_logs
	export FAKE_WT_STATUS=$1
	shift
	set +e
	"${out}/bin/wt" "$@" >"${work}/stdout" 2>"${work}/stderr"
	status=$?
	set -e
	stderr=$(cat "${work}/stderr")
}

expect_wt() {
	grep -qxF -- "$1" "${FAKE_WT_LOG}" || fail "wt log wanted '$1' got '$(cat "${FAKE_WT_LOG}")'"
}

# Failed commit with --fix: real wt sees no --fix, stderr names the omp call, omp runs.
run_wt 1 step commit --fix
[ "${status}" -eq 0 ] || fail "handoff should return omp's status, got ${status}"
expect_wt "step commit"
grep -qxF "${notice}" <<<"${stderr}" || fail "missing zsh notice in: ${stderr}"
grep -qxF '@task' "${FAKE_OMP_LOG}" || fail "omp was not invoked"
grep -qxF "${task}" "${FAKE_OMP_LOG}" || fail "omp task text mismatch: $(cat "${FAKE_OMP_LOG}")"

# Success does not call omp.
run_wt 0 step commit --fix --stage=tracked
[ "${status}" -eq 0 ] || fail "successful commit should exit 0, got ${status}"
expect_wt "step commit --stage=tracked"
[ ! -s "${FAKE_OMP_LOG}" ] || fail "omp ran after a successful commit"
[ -z "${stderr}" ] || fail "notice printed after success: ${stderr}"

# Global flags stay in front; --fix is the only token removed.
run_wt 1 -C /tmp/repo --yes step commit --fix --stage=tracked
expect_wt "-C /tmp/repo --yes step commit --stage=tracked"
grep -qxF "${task}" "${FAKE_OMP_LOG}" || fail "omp missing after -C commit"

# Without --fix, a failure is the real wt's failure. No notice, no omp.
run_wt 3 step commit
[ "${status}" -eq 3 ] || fail "plain commit should keep exit ${status}"
expect_wt "step commit"
[ ! -s "${FAKE_OMP_LOG}" ] || fail "omp ran without --fix"
[ -z "${stderr}" ] || fail "notice printed without --fix: ${stderr}"

# Other commands pass through, even when they fail.
run_wt 2 list
[ "${status}" -eq 2 ] || fail "wt list should keep exit 2, got ${status}"
expect_wt "list"
[ ! -s "${FAKE_OMP_LOG}" ] || fail "omp ran for wt list"

echo "commit-fix fixture ok"
