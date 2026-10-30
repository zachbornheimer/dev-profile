#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/worktree-copy.sh: `mise run generate` copies it into bin/.

# Worktrunk's post-start copy: `wt step copy-ignored` reflinks the source
# worktree's ignored files, which is what makes a new worktree cheap. Composer's
# optimized autoloader is the exception — autoload_classmap.php and its
# neighbours bake absolute paths — so a copied vendor/ points PHP at the source
# checkout and `php artisan` dies on the app's own classes until someone dumps
# the autoloader by hand. Do it here, so entering a worktree just works. A repo
# without a built autoloader is untouched.
#
# The repair is advisory: an autoloader that cannot be rebuilt leaves the
# worktree usable and says what to run, but never fails the start. The copy
# itself keeps its own failure, since a start without the copied files is wrong,
# once it has been retried (see below).
usage="usage: dev-profile-worktree-copy [--help]"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
	echo "${usage}"
	exit 0
fi
[[ $# -eq 0 ]] || {
	echo "${usage}" >&2
	exit 2
}

root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
	echo "dev-profile-worktree-copy: ${PWD} is not inside a git repository" >&2
	exit 2
}
cd "${root}"

# The source worktree may be serving, and a dev server rewrites its build
# output (a bundler's .mastra/ or .next/) while the copy walks it, so a file the
# copy listed can be gone by the time it is cloned. That is a race, not a broken
# copy: copy-ignored skips what already landed, so a second pass finishes the
# rest. A copy that still fails after the last pass keeps its failure.
copy_attempts="${DEV_PROFILE_WORKTREE_COPY_ATTEMPTS:-3}"
copy_retry_delay="${DEV_PROFILE_WORKTREE_COPY_RETRY_DELAY:-2}" # seconds
attempt=1
until wt step copy-ignored; do
	if ((attempt >= copy_attempts)); then
		echo "dev-profile-worktree-copy: the copy failed ${attempt} times; run: wt step copy-ignored" >&2
		exit 1
	fi
	attempt=$((attempt + 1))
	sleep "${copy_retry_delay}"
done

# Both markers: composer.json alone is a repo whose dependencies were never
# installed, and a vendor/ without autoload.php is not an autoloader to rebuild.
[[ -f composer.json && -f vendor/autoload.php ]] || exit 0

repair_timeout="${DEV_PROFILE_WORKTREE_COPY_TIMEOUT:-60}" # seconds

# Bounded without timeout(1), which a clean machine need not have: a post-start
# hook that hangs blocks every switch.
bounded() { # <seconds> <cmd...>
	local limit="$1" pid watchdog status=0
	shift
	"$@" &
	pid=$!
	(
		sleep "${limit}"
		kill -TERM "${pid}" 2>/dev/null
	) &
	watchdog=$!
	wait "${pid}" || status=$?
	kill "${watchdog}" 2>/dev/null || :
	wait "${watchdog}" 2>/dev/null || :
	return "${status}"
}

if ! command -v composer >/dev/null 2>&1; then
	reason="composer is not installed"
elif bounded "${repair_timeout}" composer dump-autoload --no-interaction --quiet; then
	echo "dev-profile-worktree-copy: rebuilt the copied Composer autoloader for this checkout"
	exit 0
else
	reason="composer dump-autoload failed"
fi
# One line, naming the fix: the checkout is usable, its vendor/ is not.
echo "dev-profile-worktree-copy: ${reason}: the copied vendor/ points at another checkout; run: composer dump-autoload" >&2
exit 0
