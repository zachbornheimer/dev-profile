#!/usr/bin/env bash
# The post-start copy wrapper against real git and stubbed worktrunk and
# composer: `wt step copy-ignored` runs first and keeps its own failure, a repo
# without a built Composer autoloader gets nothing else, a copied vendor/ gets a
# fresh one inside the deadline, and a repair that cannot run says so once and
# leaves the checkout usable. `wt` and `composer` are stubs, so no worktrunk,
# PHP or network is needed; they record every call, which is how the fixture
# proves what ran.
# Usage: worktree-copy-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: worktree-copy-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
copy="${out}/bin/dev-profile-worktree-copy"
wt_log="${work}/wt.log"
composer_log="${work}/composer.log"

fail() {
	echo "FAIL worktree-copy fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

cleanup() { rm -rf "${work}"; }
trap cleanup EXIT

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com

mkdir -p "${work}/bin"
cat >"${work}/bin/wt" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${WT_LOG}"
exit "${STUB_WT_STATUS:-0}"
STUB
cat >"${work}/bin/composer" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${COMPOSER_LOG}"
[[ -z "${STUB_COMPOSER_SLEEP:-}" ]] || sleep "${STUB_COMPOSER_SLEEP}"
exit "${STUB_COMPOSER_STATUS:-0}"
STUB
chmod +x "${work}/bin/wt" "${work}/bin/composer"
export WT_LOG="${wt_log}" COMPOSER_LOG="${composer_log}"
export PATH="${work}/bin:${PATH}"

run_copy() { "${copy}" "$@" >"${work}/output.txt" 2>&1; }

expect() { grep -qF -- "$1" "${work}/output.txt" || fail "the output must contain '$1'"; }

lines() { awk 'END { print NR }' "$1"; }

# Each case starts from a clean record, so a call from a previous case cannot
# pass for this one.
reset_logs() {
	: >"${wt_log}"
	: >"${composer_log}"
}

copied() { grep -qxF "step copy-ignored" "${wt_log}" || fail "the copy must always run wt step copy-ignored"; }

repaired() { grep -qxF "dump-autoload --no-interaction --quiet" "${composer_log}" || fail "an installed vendor must get a fresh autoloader"; }

not_repaired() {
	[[ ! -s "${composer_log}" ]] || fail "nothing here needs an autoloader, so composer must not run (ran: $(tr '\n' ' ' <"${composer_log}"))"
}

# --- --help and a bad argument: no copy, no repair

reset_logs
run_copy --help || fail "--help must exit 0"
expect 'usage: dev-profile-worktree-copy [--help]'
[[ ! -s "${wt_log}" ]] || fail "--help must not copy anything"
if run_copy --nope; then fail "an unknown argument must not be accepted"; fi
[[ ! -s "${wt_log}" ]] || fail "an unknown argument must not copy anything"

# --- a repo with nothing to repair: the copy, and silence

plain="${work}/plain"
git init -q -b main "${plain}"
cd "${plain}"
reset_logs
run_copy || fail "the wrapper must exit 0 where there is nothing to repair"
copied
not_repaired
[[ "$(lines "${work}/output.txt")" -eq 0 ]] || fail "a repo with nothing to repair must print nothing"

# --- composer.json without a built autoloader: still nothing to repair

printf '{"require":{}}\n' >composer.json
reset_logs
run_copy || fail "a repo with dependencies not yet installed must exit 0"
copied
not_repaired

# --- a copied vendor/: the autoloader is dumped again

mkdir -p vendor
printf '<?php\n' >vendor/autoload.php
reset_logs
run_copy || fail "a repo with a built autoloader must exit 0"
copied
repaired
[[ "$(lines "${composer_log}")" -eq 1 ]] || fail "the autoloader must be dumped exactly once"
expect 'rebuilt the copied Composer autoloader'

# --- a repair that fails: one clear line, the checkout still enters

reset_logs
if ! STUB_COMPOSER_STATUS=1 run_copy; then fail "a failed repair is advisory and must exit 0"; fi
expect 'composer dump-autoload failed: the copied vendor/ points at another checkout; run: composer dump-autoload'
[[ "$(lines "${work}/output.txt")" -eq 1 ]] || fail "a failed repair must be one clear line"

# --- a repair that hangs: bounded, then the same one clear line

reset_logs
start="${SECONDS}"
if ! STUB_COMPOSER_SLEEP=60 DEV_PROFILE_WORKTREE_COPY_TIMEOUT=1 run_copy; then
	fail "a hanging repair is advisory and must exit 0"
fi
elapsed=$((SECONDS - start))
[[ "${elapsed}" -lt 20 ]] || fail "the repair must give up at its deadline, took ${elapsed}s"
expect 'composer dump-autoload failed: the copied vendor/ points at another checkout; run: composer dump-autoload'

# --- composer absent: the same advice, never a stack trace

mkdir -p "${work}/bin-wt"
cp "${work}/bin/wt" "${work}/bin-wt/wt"
reset_logs
if ! PATH="${work}/bin-wt:/usr/bin:/bin" "${copy}" >"${work}/output.txt" 2>&1; then
	fail "a missing composer is advisory and must exit 0"
fi
expect 'composer is not installed: the copied vendor/ points at another checkout; run: composer dump-autoload'
[[ "$(lines "${work}/output.txt")" -eq 1 ]] || fail "a missing composer must be one clear line"

# --- the copy's own failure is not advisory: a start without the files is wrong

reset_logs
if STUB_WT_STATUS=1 run_copy; then fail "a failed copy must fail the post-start step"; fi
not_repaired

echo "worktree-copy fixture ok"
