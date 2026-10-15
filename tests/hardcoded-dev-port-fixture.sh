#!/usr/bin/env bash
# The hardcoded-dev-port push judge against real git: only lines a push adds
# are judged, so a file that already names localhost:NNNN can still be edited.
# Covers SAH_PUSH_REFS (pre-push stdin saved to a file) and the merge-base
# fallback for a branch with no remote base.
# Usage: hardcoded-dev-port-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: hardcoded-dev-port-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
judge="${out}/bin/dev-profile-hardcoded-dev-port"

fail() {
	echo "FAIL hardcoded-dev-port fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
origin="${work}/origin.git"
git init -q --bare -b main "${origin}"
repo="${work}/repo"
git clone -q "${origin}" "${repo}" 2>/dev/null
cd "${repo}"
git config commit.gpgsign false
mkdir -p app
printf 'verify: http://localhost:9000/health\napi: http://localhost:1001\n' >app/config.cue
printf 'keep\nold: http://localhost:8080\n' >app/old.cue
git add -A && git commit -qm base && git push -q origin HEAD:main
git remote set-head origin main >/dev/null
git switch -q -c feature

run_judge() { "${judge}" "$@" >"${work}/output.txt" 2>&1; }

# 1. Edit an unrelated line of a file that already holds localhost ports.
printf 'verify: http://localhost:9000/health\napi: http://localhost:1001\n# a comment\n' >app/config.cue
git commit -qam "edit unchanged-port file"
run_judge app/config.cue || fail "existing localhost lines in an unchanged region must pass (merge-base fallback)"

# 1b. Same, judged through SAH_PUSH_REFS for a new branch (remote sha all zeros).
zeros=0000000000000000000000000000000000000000
printf 'refs/heads/feature %s refs/heads/feature %s\n' "$(git rev-parse HEAD)" "${zeros}" >"${work}/refs"
SAH_PUSH_REFS="${work}/refs" run_judge app/config.cue || fail "existing localhost lines must pass (SAH_PUSH_REFS, new branch)"

# 4. Removing a line that held a port passes.
printf 'keep\n' >app/old.cue
git commit -qam "remove a port line"
run_judge app/old.cue || fail "a removed port line must pass"

# Push it so the next case has a real remote base in SAH_PUSH_REFS.
git push -q origin feature
remote_sha="$(git rev-parse HEAD)"

# 2. A newly added hardcoded port in an existing file fails.
printf 'verify: http://localhost:9000/health\napi: http://localhost:1001\n# a comment\nnew: http://localhost:5173\n' >app/config.cue
git commit -qam "add a port"
printf 'refs/heads/feature %s refs/heads/feature %s\n' "$(git rev-parse HEAD)" "${remote_sha}" >"${work}/refs"
if SAH_PUSH_REFS="${work}/refs" run_judge app/config.cue; then fail "a newly added port must fail (SAH_PUSH_REFS)"; fi
grep -Fq "localhost:5173" "${work}/output.txt" || fail "the failure must name the added line"
if grep -Fq "localhost:9000" "${work}/output.txt"; then fail "pre-existing lines must not be reported"; fi
if run_judge app/config.cue; then fail "a newly added port must fail (merge-base fallback)"; fi

# 3. A new file with a port fails.
printf 'server: http://127.0.0.1:3000\n' >app/new.cue
git add app/new.cue && git commit -qm "new file"
if run_judge app/new.cue; then fail "a new file with a port must fail"; fi
grep -Fq "127.0.0.1:3000" "${work}/output.txt" || fail "the failure must name the new file's line"

# A file that reads PORT from the environment keeps a literal fallback.
printf 'port = os.Getenv("PORT")\nfallback: "localhost:4000"\n' >app/env.go
git add app/env.go && git commit -qm "env port"
run_judge app/env.go || fail "a file that reads PORT may keep a literal fallback"

echo "hardcoded-dev-port fixture ok"
