#!/usr/bin/env bash
set -euo pipefail
runner="$(cd "$(dirname "$0")" && pwd)/run-fixtures.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export FIXTURE_EVENTS="$work/events"
mkdir -p "$work/stubs" "$work/output dir"
for name in a b c; do
	cat >"$work/$name fixture.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "$EXPECTED_OUT" ]]
echo start >>"$FIXTURE_EVENTS"
sleep 0.2
echo end >>"$FIXTURE_EVENTS"
EOF
done
export EXPECTED_OUT="$work/output dir"
peak() {
	awk '/start/ { active++; if (active > peak) peak=active } /end/ { active-- } END { print peak+0 }' "$FIXTURE_EVENTS"
}
run() {
	: >"$FIXTURE_EVENTS"
	bash "$runner" "$EXPECTED_OUT" "$work/a fixture.sh" "$work/b fixture.sh" "$work/c fixture.sh" >"$work/log" 2>&1
}
# The pool runs every named fixture once and never echoes a passing fixture.
DEV_PROFILE_DOCTOR_JOBS=1 run
[[ "$(peak)" == 1 ]]
[[ "$(wc -l <"$FIXTURE_EVENTS" | tr -d ' ')" == 6 ]]
DEV_PROFILE_DOCTOR_JOBS=2 run
[[ "$(peak)" == 2 ]]
[[ "$(wc -l <"$FIXTURE_EVENTS" | tr -d ' ')" == 6 ]]
! grep -q 'fixture ok' "$work/log" || { echo 'FAIL: a passing fixture echoed into the log' >&2; exit 1; }
# A failing fixture fails the pool, names itself, and shows its own log only.
printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'echo deliberate-failure >&2' 'exit 7' >"$work/fail.sh"
if DEV_PROFILE_DOCTOR_JOBS=2 bash "$runner" "$EXPECTED_OUT" "$work/fail.sh" "$work/a fixture.sh" >"$work/log" 2>&1; then
	echo 'FAIL: fixture failure was swallowed' >&2
	exit 1
fi
grep -q 'FAIL: fail.sh (exit 7)' "$work/log"
grep -q deliberate-failure "$work/log"
# The second worker failing never hides the first: both are named.
if DEV_PROFILE_DOCTOR_JOBS=2 bash "$runner" "$EXPECTED_OUT" "$work/fail.sh" "$work/fail.sh" >"$work/log" 2>&1; then
	echo 'FAIL: two failures were swallowed' >&2
	exit 1
fi
grep -q 'FAIL: 2 fixture(s) failed' "$work/log"
for jobs in 0 -1 nope; do
	if DEV_PROFILE_DOCTOR_JOBS="$jobs" run; then
		echo "FAIL: accepted invalid jobs: $jobs" >&2
		exit 1
	fi
done
# More workers than cores never helps: one core means one at a time.
printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'echo 1' >"$work/stubs/getconf"
chmod +x "$work/stubs/"*
PATH="$work/stubs:$PATH" DEV_PROFILE_DOCTOR_JOBS='' DEV_PROFILE_DOCTOR_MAX_JOBS=4 run
[[ "$(peak)" == 1 ]]
# A quiet machine uses the free cores, capped by the configured ceiling.
printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'echo 8' >"$work/stubs/getconf"
PATH="$work/stubs:$PATH" DEV_PROFILE_DOCTOR_JOBS='' DEV_PROFILE_DOCTOR_MAX_JOBS=2 run
[[ "$(peak)" == 2 ]]
echo 'fixture runner tests ok'
