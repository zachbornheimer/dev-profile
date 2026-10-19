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

# Only the app's own server port collides across checkouts. Addresses of other
# services the app calls, and literals that are already an env fallback, pass.
# Dependency cases run first: no listen site exists yet, so no port is "ours".
add_file() { # <path> <content>
	mkdir -p "$(dirname "$1")"
	printf '%s\n' "$2" >"$1"
	git add "$1" && git commit -qm "add $1"
}
expect_pass() { # <path> <why>
	run_judge "$1" || fail "$2 must pass: $1"
}
expect_fail() { # <path> <needle> <why>
	if run_judge "$1"; then fail "$3 must fail: $1"; fi
	grep -Fq -- "$2" "${work}/output.txt" || fail "$3: the failure must name '$2'"
}

# A dependency's address is not the app's dev port.
add_file mastra/src/mastra/hindsight.ts 'export const DEFAULT_HINDSIGHT_API_URL = "http://127.0.0.1:9077";'
add_file mastra/src/runtime/adapters/local-proxy-language.ts 'export const LOCAL_PROXY_URL = "http://127.0.0.1:8787/v1";'
add_file mastra/src/runtime/adapters/ollama-system-one.ts 'export const OLLAMA_BASE_URL = "http://localhost:11434";'
expect_pass mastra/src/mastra/hindsight.ts "a memory API address"
expect_pass mastra/src/runtime/adapters/local-proxy-language.ts "a proxy address"
expect_pass mastra/src/runtime/adapters/ollama-system-one.ts "an Ollama address"

# A literal that is the fallback of an env read on the same line is configurable.
add_file scripts/eval/propose_capabilities.sh 'LOCAL_PROXY_URL="${AGENTMUX_LOCAL_PROXY_URL:-http://127.0.0.1:8787/v1}"'
add_file scripts/smoke/propose_capabilities.sh 'LOCAL_PROXY_URL="${AGENTMUX_LOCAL_PROXY_URL:-http://127.0.0.1:8787/v1}"'
expect_pass scripts/eval/propose_capabilities.sh "a shell \${VAR:-default} fallback"
expect_pass scripts/smoke/propose_capabilities.sh "a shell \${VAR:-default} fallback"
# Same shapes on a conventional dev port, so only the fallback can excuse them.
add_file env/fallbacks.sh 'A="${API_URL:-http://localhost:3000}"'
add_file env/fallback.ts 'const a = process.env.API_URL ?? "http://localhost:5173";'
add_file env/fallback.py 'a = os.environ.get("API_URL", "http://localhost:8000")'
add_file env/fallback.go 'a := envOr("API_URL", "http://localhost:8080")'
add_file env/fallback.rb 'a = ENV.fetch("API_URL", "http://localhost:3000")'
for f in env/fallbacks.sh env/fallback.ts env/fallback.py env/fallback.go env/fallback.rb; do
	expect_pass "${f}" "an env-read fallback"
done
# The same literal with no env read still fails.
add_file env/bare.ts 'const a = "http://localhost:5173";'
expect_fail env/bare.ts "localhost:5173" "a bare conventional dev-port URL"

# The app's own server port still fails.
add_file srv/server.js 'const app = express(); app.listen(3000);'
expect_fail srv/server.js ".listen(3000" "a listen site with no PORT read"
add_file srv/docker-compose.yml '    ports:
      - "8123:80"'
expect_fail srv/docker-compose.yml '"8123:80"' "a compose published port"

# A URL on a port the repo itself listens on is the app's own address.
add_file srv/own.listen.js 'app.listen(7421);'
add_file client/own.ts 'const base = "http://localhost:7421/health";'
expect_fail client/own.ts "localhost:7421" "a URL on the port the repo's server listens on"
add_file client/other.ts 'const base = "http://localhost:7422/health";'
expect_pass client/other.ts "a URL on a port no listen site in the repo uses"

echo "hardcoded-dev-port fixture ok"
