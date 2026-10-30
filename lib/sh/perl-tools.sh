# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: `perl_config <tool> <dir>` and `require_perl_tool <tool>`, for the perltidy and
# perlcritic wrappers: the rc file at the repo root of <dir> wins, else the profile's.
# Edit lib/sh/perl-tools.sh: `mise run generate` copies it into lib/.

profile_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

# Where dev-profile-perl-tools-install puts the CPAN tools. Hooks and GUI editors
# may not have the shell's local::lib environment, so find them here.
perl_lib_root="${HOME}/perl5"
export PATH="${PATH}:${perl_lib_root}/bin"
export PERL5LIB="${perl_lib_root}/lib/perl5${PERL5LIB:+:${PERL5LIB}}"

# Fail the step, never skip it: a formatter or linter that silently does nothing is worse than none.
require_perl_tool() { # <tool>
	if ! command -v "$1" >/dev/null 2>&1; then
		echo "$1 is not installed; install it with: dev-profile-perl-tools-install" >&2
		exit 1
	fi
}

# The rc file for tool $1: the repo's own .<tool>rc at the root of the repo holding dir $2, else the profile's <tool>rc.
perl_config() { # <tool> <dir>
	local repo_root
	repo_root="$(git -C "$2" rev-parse --show-toplevel 2>/dev/null)" || repo_root="$2"
	if [[ -f "${repo_root}/.$1rc" ]]; then
		echo "${repo_root}/.$1rc"
	else
		echo "${profile_dir}/$1rc"
	fi
}
