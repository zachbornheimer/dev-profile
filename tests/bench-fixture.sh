#!/usr/bin/env bash
# WT_BENCH times `wt` and the gh/git calls behind `wt land`: off by default,
# exit statuses pass through, nested calls report as one tree.
# Usage: bench-fixture.sh <repo-root>
set -euo pipefail

root="$(cd "${1:?usage: bench-fixture.sh <repo-root>}" && pwd -P)"
bench="${root}/bin/dev-profile-bench"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL bench fixture: $*" >&2
	exit 1
}

export WT_BENCH_LOG="${work}/bench.tsv"
unset WT_BENCH WT_BENCH_RUN WT_BENCH_DEPTH

# Off: runs the command, keeps its status, writes nothing.
status=0
"${bench}" run "off" -- bash -c 'exit 7' || status=$?
[[ "${status}" -eq 7 ]] || fail "off: exit status ${status}, want 7"
[[ ! -e "${WT_BENCH_LOG}" ]] || fail "off: wrote a log"
WT_BENCH=0 "${bench}" run "off" -- true
[[ ! -e "${WT_BENCH_LOG}" ]] || fail "WT_BENCH=0 wrote a log"

# On: a parent that runs two children shares one run id and nests by depth.
inner="${work}/inner.sh"
cat >"${inner}" <<EOF
#!/usr/bin/env bash
"${bench}" run "slow child" -- bash -c 'sleep 0.2'
"${bench}" run "failing child" -- bash -c 'exit 3' || true
EOF
chmod +x "${inner}"
status=0
WT_BENCH=1 "${bench}" run "wt land" -- "${inner}" || status=$?
[[ "${status}" -eq 0 ]] || fail "on: exit status ${status}, want 0"
[[ "$(wc -l <"${WT_BENCH_LOG}")" -eq 3 ]] || fail "on: want 3 records, got $(wc -l <"${WT_BENCH_LOG}")"
[[ "$(cut -f1 "${WT_BENCH_LOG}" | sort -u | wc -l)" -eq 1 ]] || fail "on: records do not share a run id"
[[ "$(awk -F'\t' '$6 == "wt land" { print $2 }' "${WT_BENCH_LOG}")" == 0 ]] || fail "parent is not depth 0"
[[ "$(awk -F'\t' '$6 == "slow child" { print $2 }' "${WT_BENCH_LOG}")" == 1 ]] || fail "child is not depth 1"
[[ "$(awk -F'\t' '$6 == "failing child" { print $5 }' "${WT_BENCH_LOG}")" == 3 ]] || fail "child exit status not recorded"
slow_ms="$(awk -F'\t' '$6 == "slow child" { print $4 }' "${WT_BENCH_LOG}")"
((slow_ms >= 150)) || fail "slow child took ${slow_ms}ms, want >= 150"

report="$("${bench}" report)"
grep -q '^ *[0-9.]*s *[0-9.]*s  wt land' <<<"${report}" || fail "report lacks the parent line: ${report}"
grep -q '^ *[0-9.]*s *[0-9.]*s    slow child' <<<"${report}" || fail "report does not indent the child: ${report}"
grep -q '\[exit 3\]' <<<"${report}" || fail "report hides the failing child: ${report}"
"${bench}" runs 5 | grep -q 'wt land' || fail "runs lacks the run"

# The shim times `wt` through the same path and still passes arguments through.
shim="${work}/shim"
mkdir -p "${shim}" "${work}/real"
cp "${root}/bin/wt" "${root}/bin/dev-profile-bench" "${shim}/"
cat >"${work}/real/wt" <<'EOF'
#!/usr/bin/env bash
printf 'real wt: %s\n' "$*"
exit "${FAKE_WT_STATUS:-0}"
EOF
chmod +x "${work}/real/wt"
: >"${WT_BENCH_LOG}"
out="$(PATH="${shim}:${work}/real:${PATH}" WT_BENCH=1 FAKE_WT_STATUS=4 "${shim}/wt" list --full 2>&1)" && fail "shim swallowed the exit status"
[[ "${out}" == "real wt: list --full" ]] || fail "shim changed the arguments: ${out}"
[[ "$(cut -f5,6 "${WT_BENCH_LOG}")" == $'4\twt list --full' ]] || fail "shim record: $(cat "${WT_BENCH_LOG}")"
: >"${WT_BENCH_LOG}"
PATH="${shim}:${work}/real:${PATH}" "${shim}/wt" list >/dev/null
[[ ! -s "${WT_BENCH_LOG}" ]] || fail "shim logged with WT_BENCH unset"

echo "ok"
