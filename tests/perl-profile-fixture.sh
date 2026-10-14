#!/usr/bin/env bash
# The Perl wrappers apply the profile's own perltidy and perlcritic configs (a repo-root
# .perltidyrc / .perlcriticrc wins), and fail loudly when a tool is missing. Real perltidy
# and perlcritic: the proof is their output, not their arguments.
# Usage: perl-profile-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: perl-profile-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
# A home with no ~/.perltidyrc, so only the wrappers decide which config applies.
home="${work}/home"
mkdir -p "$home"
export HOME="$home"
unset PERLTIDY PERLCRITIC
export PATH="${out}/bin:${PATH}"

fail() {
	echo "FAIL perl-profile fixture: $*" >&2
	exit 1
}

new_repo() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	echo "$dir"
}

# 100 columns: perltidy's default 80-column limit wraps it; the profile's 120 keeps it.
readonly LONG_CALL='my @r = some_function("alpha_argument_one", "bravo_argument_two", "charlie_argument_three", 4);'

fixture_perltidy_uses_profile_style() {
	local repo
	repo="$(new_repo tidy-profile)"
	printf '%s\n' "$LONG_CALL" >"${repo}/a.pl"
	(cd "$repo" && dev-profile-perltidy-fix a.pl) || fail "perltidy fixer failed"
	[[ "$(wc -l <"${repo}/a.pl")" -eq 1 ]] || fail "perltidy fixer wrapped a 100-column line; it used defaults, not the profile style: $(cat "${repo}/a.pl")"
}

fixture_perltidy_repo_config_wins() {
	local repo
	repo="$(new_repo tidy-repo)"
	printf '%s\n' '--maximum-line-length=60' >"${repo}/.perltidyrc"
	printf '%s\n' "$LONG_CALL" >"${repo}/a.pl"
	(cd "$repo" && dev-profile-perltidy-fix a.pl) || fail "perltidy fixer failed with a repo config"
	[[ "$(wc -l <"${repo}/a.pl")" -gt 1 ]] || fail "a repo-root .perltidyrc must override the profile style"
}

fixture_perltidy_dprint_format() {
	local repo formatted
	repo="$(new_repo tidy-dprint)"
	grep -Fq "${out}/bin/dev-profile-perltidy-format" "${out}/dprint.jsonc" ||
		fail "the dprint perl exec must call ${out}/bin/dev-profile-perltidy-format"
	formatted="$(printf '%s\n' "$LONG_CALL" | dev-profile-perltidy-format "${repo}/a.pl")"
	[[ "$(wc -l <<<"$formatted")" -eq 1 ]] || fail "dprint formatter wrapped a 100-column line: ${formatted}"
	printf '%s\n' '--maximum-line-length=60' >"${repo}/.perltidyrc"
	formatted="$(printf '%s\n' "$LONG_CALL" | dev-profile-perltidy-format "${repo}/a.pl")"
	[[ "$(wc -l <<<"$formatted")" -gt 1 ]] || fail "dprint formatter must honour the repo-root .perltidyrc"
}

fixture_perlcritic_uses_profile_policies() {
	local repo
	repo="$(new_repo critic)"
	# Stringy eval is severity 5 by default; the profile disables it.
	cat >"${repo}/stringy.pl" <<'PERL'
my $v = eval "1 + 1";
1;
PERL
	# A two-argument open is severity 5 and stays enabled.
	cat >"${repo}/twoarg.pl" <<'PERL'
open(my $fh, "<in.txt");
1;
PERL
	(cd "$repo" && dev-profile-perlcritic stringy.pl) >"${work}/critic.txt" 2>&1 ||
		fail "perlcritic must pass a stringy eval, which the profile disables: $(cat "${work}/critic.txt")"
	if (cd "$repo" && dev-profile-perlcritic twoarg.pl) >"${work}/critic.txt" 2>&1; then
		fail "perlcritic must fail a two-argument open, a severity-5 policy the profile keeps"
	fi
	printf 'severity = 5\n' >"${repo}/.perlcriticrc"
	if (cd "$repo" && dev-profile-perlcritic stringy.pl) >"${work}/critic.txt" 2>&1; then
		fail "a repo-root .perlcriticrc must override the profile policies"
	fi
}

fixture_missing_tool_fails_loudly() {
	local repo bare="${work}/bare" tool
	mkdir -p "$bare"
	for tool in env bash git dirname; do ln -sf "$(command -v "$tool")" "${bare}/${tool}"; done
	repo="$(new_repo missing)"
	echo 'print 1;' >"${repo}/a.pl"
	assert_missing "$repo" dev-profile-perltidy-fix perltidy
	assert_missing "$repo" dev-profile-perltidy-format perltidy
	assert_missing "$repo" dev-profile-perlcritic perlcritic
}

assert_missing() { # <repo> <wrapper> <tool>
	if (cd "$1" && PATH="${work}/bare" "${out}/bin/$2" a.pl) >"${work}/missing.txt" 2>&1 </dev/null; then
		fail "$2: a missing $3 must fail, not skip"
	fi
	grep -Fq -- "$3 is not installed; install it with: dev-profile-perl-tools-install" "${work}/missing.txt" ||
		fail "$2: expected the missing-tool message naming $3 and the install command; got: $(cat "${work}/missing.txt")"
}

# The installer is a no-op when both tools resolve, and the bootstrap hook runs it.
fixture_installer_is_wired() {
	"${out}/bin/dev-profile-perl-tools-install" || fail "the installer must pass when both tools are present"
	grep -Fq "post-tools = \"${out}/bin/dev-profile-perl-tools-install\"" "${out}/mise-profile.toml" ||
		fail "mise-profile.toml must run dev-profile-perl-tools-install in the bootstrap post-tools hook"
}

fixture_perltidy_uses_profile_style
fixture_perltidy_repo_config_wins
fixture_perltidy_dprint_format
fixture_perlcritic_uses_profile_policies
fixture_missing_tool_fails_loudly
fixture_installer_is_wired
echo "perl-profile fixture ok"
