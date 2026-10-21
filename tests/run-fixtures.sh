#!/usr/bin/env bash
# Run doctor's fixtures as a pool. Each fixture builds its own repos under
# mktemp -d and reads the generated profile read-only, so they are independent;
# only the worker count and the reporting are shared.
set -euo pipefail

worker_count() {
	local jobs="${DEV_PROFILE_DOCTOR_JOBS:-}" limit="${DEV_PROFILE_DOCTOR_MAX_JOBS:-4}" cpus
	if [[ -n "$jobs" ]]; then
		[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'DEV_PROFILE_DOCTOR_JOBS must be a positive integer' >&2; return 1; }
		printf '%s\n' "$jobs"
		return
	fi
	[[ "$limit" =~ ^[1-9][0-9]*$ ]] || { echo 'DEV_PROFILE_DOCTOR_MAX_JOBS must be a positive integer' >&2; return 1; }
	cpus="$(getconf _NPROCESSORS_ONLN)"
	[[ "$cpus" =~ ^[1-9][0-9]*$ ]] || cpus=1
	if ((cpus > limit)); then cpus="$limit"; fi
	# Fixtures mostly wait on git, hk and mise rather than burn a core, so a
	# bounded pool shortens the run even on a loaded machine; the ceiling is what
	# keeps it from swamping one.
	printf '%s\n' "$cpus"
}

run_one() {
	local out="$1" logs="$2" fixture="$3" name started="$SECONDS" status=0
	name="${fixture##*/}"
	printf 'doctor: %s\n' "$name" >&2
	if [[ "$name" == escape-hatch-fixture.sh ]]; then
		bash "$fixture" README.md "$out" >"$logs/$name.log" 2>&1 || status=$?
	else
		bash "$fixture" "$out" >"$logs/$name.log" 2>&1 || status=$?
	fi
	printf '%s\n' "$status" >"$logs/$name.status"
	printf 'doctor: %s exit %s (%ss)\n' "$name" "$status" "$((SECONDS - started))" >&2
	# The status file carries the verdict, so one failure never aborts the pool.
	return 0
}

main() {
	local out="${1:?usage: run-fixtures.sh <generated-dir> <fixtures...>}" jobs logs fixture status failed=0
	shift
	(($#)) || { echo 'No fixtures supplied' >&2; return 1; }
	jobs="$(worker_count)" || return 1
	logs="$(mktemp -d)"
	trap 'rm -rf "$logs"' EXIT
	printf 'doctor: %s fixture worker(s)\n' "$jobs" >&2
	printf '%s\0' "$@" | xargs -0 -P "$jobs" -n 1 bash "$0" --fixture "$out" "$logs"
	for fixture in "$@"; do
		status="$(cat "$logs/${fixture##*/}.status" 2>/dev/null || echo missing)"
		[[ "$status" == 0 ]] && continue
		failed=$((failed + 1))
		printf 'FAIL: %s (exit %s)\n' "${fixture##*/}" "$status" >&2
		[[ ! -f "$logs/${fixture##*/}.log" ]] || cat "$logs/${fixture##*/}.log" >&2
	done
	# Cleanup runs here, not in an EXIT trap: the trap would fire after main's
	# locals left scope, where `logs` is unset under `set -u`.
	rm -rf "$logs"
	trap - EXIT
	((failed == 0)) || { printf 'FAIL: %s fixture(s) failed\n' "$failed" >&2; return 1; }
}

if [[ "${1:-}" == --fixture ]]; then
	shift
	run_one "$@"
else
	main "$@"
fi
