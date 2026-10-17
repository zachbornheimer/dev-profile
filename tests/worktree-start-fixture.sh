#!/usr/bin/env bash
# The single post-start entry against real git and stubbed worktrunk, composer and
# mise: the copy runs first and keeps its own failure, the stack starts through
# `mise run dev` and never through a dispatcher binary, a checkout with nothing to
# serve exits 0 and silent, and a repeat run copies once. `wt`, `composer`, `mise`
# and the dev dispatcher are stubs, so no worktrunk, PHP, network or profile is
# needed; they append to one log, which is how the fixture proves the order.
# Usage: worktree-start-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: worktree-start-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
start="${out}/bin/dev-profile-worktree-start"
log="${work}/calls.log"

fail() {
	echo "FAIL worktree-start fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	[[ ! -f "${log}" ]] || sed 's/^/  | /' "${log}" >&2
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
printf 'wt %s\n' "$*" >>"${CALLS}"
exit "${STUB_WT_STATUS:-0}"
STUB
cat >"${work}/bin/composer" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'composer %s\n' "$*" >>"${CALLS}"
exit "${STUB_COMPOSER_STATUS:-0}"
STUB
# The family's own probes, answering like the real ones: `dev:status` exits
# non-zero whenever the checkout is not serving.
cat >"${work}/bin/mise" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'mise %s\n' "$*" >>"${CALLS}"
if [[ "${1:-}" == run && "${2:-}" == dev:status ]]; then
	echo "${STUB_STATUS:-state=down}"
	[[ "${STUB_STATUS:-state=down}" == state=running* ]] && exit 0
	exit 1
fi
exit 0
STUB
# A dispatcher binary that must never be called: the entry goes through mise, so
# each code root's own profile decides which dispatcher `dev` is.
cat >"${work}/bin/dev-profile-dev" <<'STUB'
#!/usr/bin/env bash
printf 'dev-profile-dev %s\n' "$*" >>"${CALLS}"
exit 1
STUB
chmod +x "${work}"/bin/*
export CALLS="${log}"
export PATH="${work}/bin:${PATH}"

run_start() { "${start}" "$@" >"${work}/output.txt" 2>&1; }

# Each case starts from a clean record, so a call from a previous case cannot
# pass for this one.
reset_log() { : >"${log}"; }

# The whole record, in order: what ran, and in which order it ran.
called() { [[ "$(cat "${log}")" == "$1" ]] || fail "the calls must be $(printf '%q' "$1"), were $(printf '%q' "$(cat "${log}")")"; }

lines() { awk 'END { print NR }' "$1"; }

# One checkout per case: the copy marker is per checkout, so a shared repo would
# hide whether the copy ran.
new_repo() { # <dir>
	git init -q -b main "$1"
	printf '{"require":{}}\n' >"$1/composer.json"
	mkdir -p "$1/vendor"
	printf '<?php\n' >"$1/vendor/autoload.php"
	(
		cd "$1"
		git add -A
		git commit -qm base
	)
}

copy_composer_start=$'wt step copy-ignored\ncomposer dump-autoload --no-interaction --quiet\nmise run dev'

# --- --help, a bad argument, no repository: nothing runs

reset_log
run_start --help || fail "--help must exit 0"
grep -qF 'usage: dev-profile-worktree-start [--help]' "${work}/output.txt" || fail "--help must print the usage"
if run_start --nope; then fail "an unknown argument must not be accepted"; fi
mkdir -p "${work}/nogit"
cd "${work}/nogit"
if run_start; then fail "a directory outside a repository must not be accepted"; fi
called ""

# --- a checkout with a built vendor/: copy, repair, then start through mise

repo="${work}/repo"
new_repo "${repo}"
cd "${repo}"
reset_log
run_start || fail "the entry must exit 0 where the checkout serves"
called "${copy_composer_start}"
grep -qF 'rebuilt the copied Composer autoloader for this checkout' "${work}/output.txt" ||
	fail "the repair must still name what it did"
[[ -e "$(git rev-parse --git-dir)/.worktree-copied" ]] || fail "the copy must leave its per-checkout marker"

# --- the same checkout again: no second copy, the stack is still asked for

reset_log
run_start || fail "a repeat run must exit 0"
called 'mise run dev'

# --- nothing to serve: the copy, then silence and success

quiet="${work}/quiet"
git init -q -b main "${quiet}"
cd "${quiet}"
reset_log
if ! run_start; then fail "a checkout with nothing to serve must exit 0"; fi
called 'wt step copy-ignored'
[[ "$(lines "${work}/output.txt")" -eq 0 ]] || fail "nothing to serve must be silent"

# --- a failed copy is not advisory: the stack never starts

broken="${work}/broken"
new_repo "${broken}"
cd "${broken}"
reset_log
STUB_WT_STATUS=1
export STUB_WT_STATUS
if run_start; then fail "a failed copy must fail the entry"; fi
unset STUB_WT_STATUS
called "wt step copy-ignored"

# --- a failed repair is advisory: one line, and the stack still starts

advisory="${work}/advisory"
new_repo "${advisory}"
cd "${advisory}"
reset_log
STUB_COMPOSER_STATUS=1
export STUB_COMPOSER_STATUS
if ! run_start; then fail "a failed repair is advisory and must exit 0"; fi
unset STUB_COMPOSER_STATUS
called "${copy_composer_start}"
grep -qF 'composer dump-autoload failed: the copied vendor/ points at another checkout; run: composer dump-autoload' "${work}/output.txt" ||
	fail "a failed repair must name the fix"

echo "worktree-start fixture ok"
