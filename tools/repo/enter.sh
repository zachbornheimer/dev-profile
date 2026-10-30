#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/enter.sh: `mise run generate` copies it into bin/.
# The on-cd worker: everything a directory needs, off the interactive path.
# A chpwd hook only forks it and returns, so `cd` costs one fork. One worker
# per checkout (flock), and it never prompts: an untrusted config is skipped.

# Called detached from a shell's chpwd hook (`dev-profile-enter "$PWD" &!`).
# Installs tools and deps, fills node_modules, starts the portless proxy, then
# hands the decision to the profile's `dev` family, which starts the stack
# under worktrunk's tether (killed when the worktree goes) or answers
# state=unconfigured in a checkout that serves nothing.
set -uo pipefail
target="${1:-$PWD}"
root="$(command git -C "${target}" rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "${root}" 2>/dev/null || exit 0
[[ ${DEV_PROFILE_ENTER_DISABLE:-0} == 1 ]] && exit 0

cache="${XDG_CACHE_HOME:-${HOME}/.cache}/dev-profile/enter"
command mkdir -p "${cache}" || exit 0
name="$(printf '%s' "$(basename "${root}")" | tr '[:upper:]' '[:lower:]' |
	sed -e 's/[^a-z0-9]/-/g' -e 's/--*/-/g' -e 's/^-*//' -e 's/-*$//')"
exec >>"${cache}/${name}.log" 2>&1
# One worker per checkout: a second cd while the first runs is a no-op.
if command -v flock >/dev/null 2>&1; then
	exec 9>"${cache}/${name}.lock"
	command flock -n 9 || exit 0
fi
printf '== %s %s\n' "$(date '+%F %T')" "${root}"

# Trust without ever prompting: only repos this profile owns, and only once.
if ! command mise trust --show 2>/dev/null | command grep -q ': trusted'; then
	case "$(command git remote get-url origin 2>/dev/null)" in
	*github.com/zysys/* | *github.com/zachbornheimer/* | *github.com/software-automation-holdings/* | *github.com:zysys/* | *github.com:zachbornheimer/* | *github.com:software-automation-holdings/*)
		command mise trust --yes >/dev/null 2>&1 || true
		;;
	*)
		printf 'skip untrusted: %s\n' "${root}"
		exit 0
		;;
	esac
fi

# No `mise install` here: auto_install installs a missing tool the first time
# it runs, and a blanket install at every cd is what made cd feel slow.
command mise deps || true
# A repo that predates the deps providers still gets its modules.
if [[ -f package.json && ! -d node_modules ]]; then
	if [[ -f pnpm-lock.yaml ]]; then
		command pnpm install || true
	elif [[ -f bun.lock || -f bun.lockb ]]; then
		command bun install || true
	else
		command aube install || true
	fi
fi
# Routes are <name>.localhost: they need the proxy, never a prompt.
command portless proxy start >/dev/null 2>&1 || true
command mise run dev
