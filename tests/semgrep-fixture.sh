#!/usr/bin/env bash
# The commit-time semgrep step blocks a finding, passes clean code, and never
# makes a commit depend on semgrep.dev while any cached pack exists.
# The registry is a curl stub, so the fixture is offline and deterministic.
# Usage: semgrep-fixture.sh [helper]   (default: this repo's bin/dev-profile-semgrep)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
helper="${1:-${root}/bin/dev-profile-semgrep}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL semgrep fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

command -v semgrep >/dev/null 2>&1 || fail "semgrep is not installed; it is pinned in config/tools.toml"

# curl stub: logs each call, then behaves as an unreachable registry.
mkdir -p "${work}/stubs"
printf '#!/usr/bin/env bash\necho "$*" >>"%s/curl.log"\nexit 6\n' "${work}" >"${work}/stubs/curl"
chmod +x "${work}/stubs/curl"
export PATH="${work}/stubs:${PATH}" XDG_CACHE_HOME="${work}/cache"
rules="${work}/cache/dev-profile/semgrep/typescript.yml"

seed_cache() {
	mkdir -p "$(dirname "${rules}")"
	cat >"${rules}" <<'YAML'
rules:
  - id: fixture-eval
    languages: [typescript]
    severity: ERROR
    message: eval of a dynamic value
    pattern: eval($X)
YAML
}

# Semgrep runs where hk runs it: the repo root, with repo-relative paths.
git init -q "${work}/repo"
cd "${work}/repo"
printf 'export function run(input: string) {\n  return eval(input)\n}\n' >bad.ts
printf 'export const answer: number = 42\n' >clean.ts

run_helper() {
	: >"${work}/curl.log"
	"${helper}" "$@" >"${work}/output.txt" 2>&1
}

# 1. A fresh cache is used as-is: the finding blocks and the registry is not called.
seed_cache
if run_helper bad.ts; then fail "a finding must fail the step"; fi
grep -qF "fixture-eval" "${work}/output.txt" || fail "the failure must name the rule"
[[ ! -s "${work}/curl.log" ]] || fail "a fresh cache must not call the registry"

# 2. Clean code passes.
run_helper clean.ts || fail "clean code must pass"

# 3. A stale cache is still used when the registry is unreachable.
touch -t 202001010000 "${rules}"
if run_helper bad.ts; then fail "a stale cache must still judge when the registry is down"; fi
grep -qF "fixture-eval" "${work}/output.txt" || fail "the stale-cache failure must name the rule"
[[ -s "${work}/curl.log" ]] || fail "a stale cache must try to refresh"
run_helper bad.ts || true
[[ ! -s "${work}/curl.log" ]] || fail "a failed refresh must not be retried on the next commit"

# 4. No cache and no registry: fail with the fix, never pass silently.
rm -f "${rules}"
if run_helper clean.ts; then fail "with no rules at all the step must fail"; fi
grep -qF "HK=0" "${work}/output.txt" || fail "the no-rules failure must print the bypass"

# 5. No files: nothing to judge.
rm -f "${work}/curl.log"
"${helper}" >"${work}/output.txt" 2>&1 || fail "no files must pass"
[[ ! -e "${work}/curl.log" ]] || fail "no files must not call the registry"

# 6. A hung scan is stopped at the limit and fails the step instead of hanging the commit.
seed_cache
mkdir -p "${work}/hung"
printf '#!/usr/bin/env bash\nsleep 30\n' >"${work}/hung/semgrep"
chmod +x "${work}/hung/semgrep"
start="${SECONDS}"
if PATH="${work}/hung:${PATH}" DEV_PROFILE_SEMGREP_TIMEOUT=1 run_helper clean.ts; then fail "a hung scan must fail"; fi
((SECONDS - start < 10)) || fail "a hung scan must be stopped at the limit"
grep -qF "exceeded 1s" "${work}/output.txt" || fail "the timeout failure must say so"

echo "semgrep fixture ok"
