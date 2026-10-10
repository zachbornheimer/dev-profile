#!/usr/bin/env bash
# `mise run bump` rewrites outdated pins and nothing else: a stub stands in for
# `mise latest`. Runs on a copy of the sources; real pkl, no network.
# Usage: bump-fixture.sh <generated-dir>
set -euo pipefail

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL bump fixture: $*" >&2
	exit 1
}

# A repo-shaped copy: the task finds its root with git.
cp -R "${src}/profile.pkl" "${src}/lib" "${src}/tools" "${src}/tests" "${src}/mise-tasks" "${src}/mise.toml" "${work}/"
git -C "$work" init -q

# The stub: a few releases ahead of the pins, everything else as pinned.
stub="${work}/latest"
cat >"$stub" <<'STUB'
#!/usr/bin/env bash
case "$1" in
	hk) echo "${STUB_HK:-2.5.0}" ;;         # the package URIs follow this pin
	go) echo 1.28.1 ;;                      # major.minor pin keeps its depth
	ruff) echo 0.17.0 ;;                    # a tool pin in tools/
	npm:@dprint/json) echo 0.26.0 ;;        # dprint plugin from npm
	github:g-plane/malva) echo v0.17.0 ;;   # dprint plugin from GitHub, leading v
	node) echo 26.11.1 ;;                   # major-only pin: held, never moved
	*) exit 1 ;;                            # unknown: skipped, never rewritten
esac
STUB
chmod +x ""$stub

summary=""$work/summary.md
(cd ""$work && BUMP_LATEST=""$stub BUMP_SUMMARY=""$summary bash mise-tasks/bump >/dev/null 2>""$work/stderr) ||
	fail "task failed: "$(cat "${work}/stderr")

expect() { # <file> <needle>
	grep -qF -- ""$2 ""$work/$1 || fail ""$1" lacks: "$2
}
expect profile.pkl 'id = "hk"; version = "2.5.0"'
expect profile.pkl 'id = "go"; version = "1.28"'
expect profile.pkl 'id = "node"; version = "24"'
expect profile.pkl '"npm:@dprint/json@0.26.0"'
expect profile.pkl 'malva-v0.17.0.wasm'
expect profile.pkl 'markup_fmt-v0.27.5.wasm'
expect tools/python/ruff.pkl 'version = "0.17.0"'
expect tests/profile.test.pkl-expected.pcf '["ruff"] = "0.17.0"'
expect summary.md '| ruff | 0.16.10 | 0.17.0 |'
expect summary.md '| go | 1.27 | 1.28 |'
grep -qF '| node |' ""$summary && fail "node must not be bumped: a major-only pin is held"
expect profile.pkl 'id = "node"; version = "24"'
grep -qF 'Held, a major-only pin moves by hand: node 24 -> 26' ""$summary || fail "the held pin must be reported"
grep -qF 'Lookups that failed' ""$summary || fail "the summary must list the lookups the stub refused"
grep -qE 'Lookups that failed.* dprint( |$)' ""$summary || fail "dprint's failed lookup must be listed"

# Nothing newer and some lookups failed: the task must say so and fail rather
# than claim every pin is current.
rm -rf "${work}/quiet" && mkdir "${work}/quiet"
cp -R "${src}/profile.pkl" "${src}/lib" "${src}/tools" "${src}/tests" "${src}/mise-tasks" "${src}/mise.toml" "${work}/quiet/"
git -C "${work}/quiet" init -q
if (cd "${work}/quiet" && BUMP_LATEST=false bash mise-tasks/bump >/dev/null 2>"${work}/quiet.err"); then
	fail "all lookups failing must fail the task"
fi
grep -q 'lookup(s) failed' "${work}/quiet.err" || fail "failed lookups must be reported: $(cat "${work}/quiet.err")"
for part in profile.pkl lib tools; do
	diff -rq "${src}/${part}" "${work}/quiet/${part}" >/dev/null || fail "nothing may be rewritten when no lookup succeeds: ${part}"
done

# A new hk moves the package URIs with the pin. No such release exists, so the
# snapshot step must fail and the task with it; the rewrite itself must be done.
rm -rf "${work}/again" && mkdir "${work}/again"
cp -R "${src}/profile.pkl" "${src}/lib" "${src}/tools" "${src}/tests" "${src}/mise-tasks" "${src}/mise.toml" "${work}/again/"
git -C "${work}/again" init -q
if (cd "${work}/again" && STUB_HK=2.6.1 BUMP_LATEST="${stub}" bash mise-tasks/bump >/dev/null 2>&1); then
	fail "hk 2.6.1: a package that does not resolve must fail the task"
fi
expect again/profile.pkl 'id = "hk"; version = "2.6.1"'
expect again/lib/hk.pkl 'download/v2.6.1/hk@2.6.1#/Config.pkl'
expect again/lib/Tool.pkl 'download/v2.6.1/hk@2.6.1#/Builtins.pkl'
expect again/tests/profile.test.pkl 'download/v2.6.1/hk@2.6.1#/Config.pkl'
grep -rqF 'hk@2.5.0' "${work}/again/lib" "${work}/again/profile.pkl" && fail "an old hk package URI remains"

# Without BUMP_LATEST the task asks `mise latest` itself, as the weekly job does.
rm -rf "${work}/default" && mkdir -p "${work}/default" "${work}/bin"
cp -R "${src}/profile.pkl" "${src}/lib" "${src}/tools" "${src}/tests" "${src}/mise-tasks" "${src}/mise.toml" "${work}/default/"
git -C "${work}/default" init -q
cat >"${work}/bin/mise" <<STUB
#!/usr/bin/env bash
[[ "\$1" == latest ]] || exit 1
shift
exec "${stub}" "\$@"
STUB
chmod +x "${work}/bin/mise"
(cd "${work}/default" && PATH="${work}/bin:${PATH}" bash mise-tasks/bump >/dev/null 2>"${work}/default.err") ||
	fail "the default lookup must reach mise latest: $(cat "${work}/default.err")"
expect default/tools/python/ruff.pkl 'version = "0.17.0"'
echo "bump fixture ok"
