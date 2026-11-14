#!/usr/bin/env bash
# The mise shell init (shell/mise.zsh): environment follows the directory, an
# in-place mise.toml edit refreshes on the next prompt without a cd, and a shell
# started in a deleted directory (PWD is ".") still finishes startup.
set -euo pipefail

# The generated-dir argument predates sourcing shell/mise.zsh directly; accepted
# so existing callers keep working, never read.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
init="${root}/shell/mise.zsh"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

project="${work}/project"
mkdir -p "${project}"
printf '[env]\nSHELL_INIT_TEST = "one"\n' >"${project}/mise.toml"

fail() {
	echo "FAIL shell-init fixture: $*" >&2
	exit 1
}

output="$(
cd "${project}" &&
	DEV_PROFILE_INIT="${init}" TEST_PROJECT="${project}" \
		MISE_TRUSTED_CONFIG_PATHS="${project}" \
		zsh -f -i -c '
				source "${DEV_PROFILE_INIT}"
				print -r -- "start=${SHELL_INIT_TEST:-missing}"
				builtin cd /tmp
				print -r -- "cd-returned=${SHELL_INIT_TEST:-missing}"
				_dev_profile_async_wait
				print -r -- "away=${SHELL_INIT_TEST:-missing}"
				builtin cd "${TEST_PROJECT}"
				_dev_profile_async_wait
				print -r -- "back=${SHELL_INIT_TEST:-missing}"
				printf "[env]\nSHELL_INIT_TEST = \"two\"\n" >mise.toml
				touch -t 203001010000 mise.toml
				_dev_profile_mise_refresh
				_dev_profile_async_wait
				print -r -- "edited=${SHELL_INIT_TEST:-missing}"
			'
)" || fail "zsh shell init failed"

expect() { grep -qxF "$1" <<<"${output}" || fail "missing '$1' in: ${output}"; }
expect "start=one"
# cd must return before the hook lands: the old environment is still in place.
expect "cd-returned=one"
expect "away=missing"
expect "back=one"
expect "edited=two"

# A deleted cwd leaves PWD as ".", where ${dir:h} never reaches "/". Startup must
# finish; a bounded watchdog kills a spinning shell so no busy child leaks.
gone="${work}/gone"
mkdir -p "${gone}"
(
	cd "${gone}" && rmdir "${gone}"
	DEV_PROFILE_INIT="${init}" zsh -f -i -c '
		source "${DEV_PROFILE_INIT}"
		print -r -- "deleted-cwd=finished"
	' >"${work}/deleted.out" 2>&1 </dev/null &
	pid=$!
	for _ in $(seq 1 100); do
		kill -0 "${pid}" 2>/dev/null || break
		sleep 0.1
	done
	if kill -0 "${pid}" 2>/dev/null; then
		kill -9 "${pid}" 2>/dev/null || true
		wait "${pid}" 2>/dev/null || true
		exit 3
	fi
	wait "${pid}"
) || fail "shell started in a deleted directory did not finish startup within 10s: $(cat "${work}/deleted.out" 2>/dev/null)"
grep -qxF "deleted-cwd=finished" "${work}/deleted.out" || fail "deleted-cwd startup output: $(cat "${work}/deleted.out")"

# Ancestor configuration must still count: a nested directory sees the parent's
# mise.toml mtime (set far in the future so no home config can outrank it).
nested="${project}/a/b"
mkdir -p "${nested}"
touch -t 203501010000 "${project}/mise.toml"
stamp="$(cd "${nested}" && HOME="${work}/home" DEV_PROFILE_INIT="${init}" zsh -f -i -c '
	source "${DEV_PROFILE_INIT}"
	print -r -- "${_DEV_PROFILE_MISE_NEW}"
' 2>/dev/null </dev/null | tail -n 1)"
expected="$(zsh -f -c 'zmodload zsh/stat; zstat +mtime -- "$1"' _ "${project}/mise.toml")"
[[ "${stamp}" == "${expected}" ]] || fail "ancestor mise.toml mtime not detected: got '${stamp}', want '${expected}'"
echo "shell-init fixture ok"
