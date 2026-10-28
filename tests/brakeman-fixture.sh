#!/usr/bin/env bash
# Brakeman at pre-push takes an application path, so the pushed files must reach it
# as ONE comma-joined --only-files argument, spaces in a name intact. Runs the real
# rendered check text against a fake `mise` and a fake `brakeman` on PATH.
# Usage: brakeman-fixture.sh
set -euo pipefail

work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL brakeman fixture: $*" >&2
	exit 1
}

mkdir -p "${work}/bin"
# `mise exec ruby@4 -- <cmd…>`: record the argv of <cmd…>, one argument per line.
cat >"${work}/bin/mise" <<'MISE'
#!/usr/bin/env bash
[[ "$1" == exec && "$2" == ruby@4 && "$3" == -- ]] || { echo "unexpected mise argv: $*" >&2; exit 64; }
shift 3
printf '%s\n' "$@" >"${FIXTURE_ARGV}"
MISE
printf '#!/bin/sh\nexit 0\n' >"${work}/bin/brakeman"
cat >"${work}/bin/dev-profile-if-installed" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
tool="${1:?}"
shift
command -v "${tool}" >/dev/null 2>&1 || exit 0
exec "$@"
WRAP
chmod +x "${work}/bin/"*

check="$(pkl eval -x 'checks["brakeman"].check' profile.pkl)"
[[ "$check" == *'{{files}}' ]] || fail "check no longer ends in {{files}}: $check"

# hk substitutes {{files}} with each pushed file shell-quoted, space-separated.
run_check() {
	local files="" f
	for f in "$@"; do files+=" $(printf '%q' "$f")"; done
	FIXTURE_ARGV="${work}/argv" PATH="${work}/bin:${PATH}" bash -c "${check//'{{files/}}'/${files# }}"
}

run_check "app/models/a.rb" "app/my dir/b c.rb" || fail "check exited non-zero"
expected=$'-q\n-w2\n--only-files\napp/models/a.rb,app/my dir/b c.rb'
[[ "$(cat "${work}/argv")" == "brakeman"$'\n'"${expected}" ]] || fail "unexpected brakeman argv: $(cat "${work}/argv")"

run_check "only.rb" || fail "single file: check exited non-zero"
[[ "$(cat "${work}/argv")" == $'brakeman\n-q\n-w2\n--only-files\nonly.rb' ]] || fail "single file argv: $(cat "${work}/argv")"

echo "brakeman fixture ok"
