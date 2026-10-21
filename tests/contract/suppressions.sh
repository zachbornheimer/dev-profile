#!/usr/bin/env bash
# Contract fixtures for the suppressions report and its enforce mode.
# Usage: suppressions.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
out='' work='' output='' profile=''
. "$(dirname "$0")/world.sh" "$@"

fixture_suppressions() {
	local repo enforce="${work}/enforce-suppressions"
	repo="$(new_repo suppressions)"
	# The directive is assembled at runtime so this file never contains it.
	printf 'package s\n\n// %s%s:all\nvar x = 1\n' "no" "lint" >"${repo}/s.go"
	commit_all "$repo"
	(cd "$repo" && dev-profile-suppressions --tree) >"$output" 2>&1 ||
		fail "suppressions: report mode must not block"
	expect_output "s.go:3:" "suppressions report"
	expect_output "report mode: 1 inline suppression(s)" "suppressions report"

	DEV_PROFILE_OUT="$out" pkl eval -p suppressionMode=enforce \
		-x 'output.files["bin/dev-profile-suppressions"].text' "$profile" >"$enforce"
	for mode in --tree --unpushed; do
		if (cd "$repo" && bash "$enforce" "$mode") >"$output" 2>&1; then
			fail "suppressions: enforce mode must block (${mode})"
		fi
		expect_output "1 inline suppression(s)" "suppressions enforce ${mode}"
	done
}

fixture_suppressions_language_scope() {
	local repo enforce="${work}/enforce-suppressions-scope"
	repo="$(new_repo suppressions-scope)"
	# Directives are assembled at runtime so this file never contains them.
	local noqa="# no""qa" tsi="// @ts-""ignore" nol="//no""lint"
	DEV_PROFILE_OUT="$out" pkl eval -p suppressionMode=enforce \
		-x 'output.files["bin/dev-profile-suppressions"].text' "$profile" >"$enforce"

	# Prose that forbids suppressions, in files of no suppressing language.
	printf 'Never write %s or %s or %s.\n' "$noqa" "$tsi" "$nol" >"${repo}/prompt.templ"
	printf 'Never write %s or %s or %s.\n' "$noqa" "$tsi" "$nol" >"${repo}/guide.md"
	commit_all "$repo"
	(cd "$repo" && bash "$enforce" --tree) >"$output" 2>&1 ||
		fail "suppressions scope: prose in .templ/.md must not be flagged"

	# Real suppressions in their own language still block.
	printf 'x = 1  %s\n' "$noqa" >"${repo}/a.py"
	printf '%s\nconst x = 1\n' "$tsi" >"${repo}/a.ts"
	printf 'package s\n\n%s\nvar x = 1\n' "$nol" >"${repo}/a.go"
	commit_all "$repo"
	if (cd "$repo" && bash "$enforce" --tree) >"$output" 2>&1; then
		fail "suppressions scope: real suppressions must block"
	fi
	expect_output "3 inline suppression(s)" "suppressions scope"
	expect_output "a.py:1:" "suppressions scope"
	expect_output "a.ts:1:" "suppressions scope"
	expect_output "a.go:3:" "suppressions scope"
}

fixture_suppressions_semgrep() {
	local repo enforce="${work}/enforce-suppressions-semgrep"
	repo="$(new_repo suppressions-semgrep)"
	# Directives are assembled at runtime so this file never contains them.
	local slash="// no""semgrep" hash="# no""semgrep"
	DEV_PROFILE_OUT="$out" pkl eval -p suppressionMode=enforce \
		-x 'output.files["bin/dev-profile-suppressions"].text' "$profile" >"$enforce"

	printf 'Never write %s or %s.\n' "$slash" "$hash" >"${repo}/guide.md"
	printf 'Never write %s or %s.\n' "$slash" "$hash" >"${repo}/prompt.templ"
	commit_all "$repo"
	(cd "$repo" && bash "$enforce" --tree) >"$output" 2>&1 ||
		fail "semgrep suppression: prose in .md/.templ must not be flagged"

	printf 'package s\n\nvar x = 1 %s\n' "$slash" >"${repo}/a.go"
	printf 'x = 1  %s\n' "$hash" >"${repo}/a.py"
	commit_all "$repo"
	if (cd "$repo" && bash "$enforce" --tree) >"$output" 2>&1; then
		fail "semgrep suppression: real directives must block"
	fi
	expect_output "2 inline suppression(s)" "semgrep suppression"
	expect_output "a.go:3:" "semgrep suppression"
	expect_output "a.py:1:" "semgrep suppression"
}

fixture_suppressions
fixture_suppressions_language_scope
fixture_suppressions_semgrep
echo "contract suppression fixtures ok"
