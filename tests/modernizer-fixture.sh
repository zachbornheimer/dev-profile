#!/usr/bin/env bash
# Commit modernizers: each wrapper runs its tool on the staged files only, and
# skips cleanly when the tool or its config is absent. Real git; tools are stubs.
# Usage: modernizer-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: modernizer-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
export HK=0

fail() {
	echo "FAIL modernizer fixture: $*" >&2
	exit 1
}

log="${work}/calls.log"
stubs="${work}/stubs"
mkdir -p "$stubs"
cp "$(dirname "$0")/logging-stub.sh" "${stubs}/stub"
for tool in cargo dotnet stylelint perltidy clang-tidy; do ln -s stub "${stubs}/${tool}"; done
export STUB_LOG="$log" STUB_EXIT=0

new_repo() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	echo "$dir"
}

# Run a generated wrapper inside a repo with the stubs on PATH.
run_wrapper() {
	local repo="$1" wrapper="$2"
	shift 2
	: >"$log"
	(cd "$repo" && PATH="${stubs}:${out}/bin:${PATH}" "${out}/bin/${wrapper}" "$@")
}

expect_call() { grep -qxF -- "$1" "$log" || fail "$2: expected call '$1'; got: $(cat "$log")"; }
expect_no_call() { [[ ! -s "$log" ]] || fail "$1: expected no tool call; got: $(cat "$log")"; }

fixture_ruff_modernize_rules() {
	grep -qF -- "--extend-select UP,FURB,SIM,PERF,C4,PIE" "${out}/src/tools/python/ruff.pkl" ||
		fail "ruff: the commit fixer must select the modernize rule families"
}

fixture_rector() {
	local repo
	repo="$(new_repo rector)"
	mkdir -p "${repo}/vendor/bin"
	ln -s "${stubs}/stub" "${repo}/vendor/bin/rector"
	echo '<?php' >"${repo}/a.php"
	run_wrapper "$repo" dev-profile-rector-fix a.php || fail "rector: skip without rector.php must pass"
	expect_no_call "rector without rector.php"
	echo '<?php return null;' >"${repo}/rector.php"
	run_wrapper "$repo" dev-profile-rector-fix a.php || fail "rector: failed"
	expect_call "rector|${repo}|process --no-progress-bar --no-diffs --clear-cache --config rector.php a.php" "rector"
}

fixture_clippy() {
	local repo
	repo="$(new_repo clippy)"
	mkdir -p "${repo}/crate/src" "${repo}/other/src"
	echo '[package]' >"${repo}/crate/Cargo.toml"
	echo '[package]' >"${repo}/other/Cargo.toml"
	echo 'fn main() {}' >"${repo}/crate/src/main.rs"
	echo 'fn main() {}' >"${repo}/other/src/main.rs"
	git -C "$repo" add .
	git -C "$repo" -c user.email=t@example.com -c user.name=t commit -q -m "chore: seed"
	echo '// staged' >>"${repo}/crate/src/main.rs"
	git -C "$repo" add crate/src/main.rs
	run_wrapper "$repo" dev-profile-clippy-fix crate/src/main.rs || fail "clippy: failed"
	expect_call "cargo|${repo}/crate|clippy --fix --allow-dirty --allow-staged --quiet" "clippy staged crate"
	grep -qF "${repo}/other" "$log" && fail "clippy: an untouched crate was fixed"
	echo '// unstaged' >>"${repo}/crate/src/main.rs"
	run_wrapper "$repo" dev-profile-clippy-fix crate/src/main.rs || fail "clippy: unstaged skip failed"
	grep -qF -- "--fix" "$log" && fail "clippy: a crate with unstaged edits must be skipped"
	return 0
}

fixture_dotnet() {
	local repo
	repo="$(new_repo dotnet)"
	mkdir -p "${repo}/app"
	touch "${repo}/app/App.sln"
	echo 'class A {}' >"${repo}/app/A.cs"
	run_wrapper "$repo" dev-profile-dotnet-format-fix app/A.cs || fail "dotnet: failed"
	expect_call "dotnet|${repo}/app|format --no-restore --include ${repo}/app/A.cs" "dotnet"
	echo 'class B {}' >"${repo}/B.cs"
	run_wrapper "$repo" dev-profile-dotnet-format-fix B.cs || fail "dotnet: no project must pass"
	expect_no_call "dotnet without a project"
}

fixture_stylelint() {
	local repo
	repo="$(new_repo stylelint)"
	echo 'a{}' >"${repo}/a.css"
	run_wrapper "$repo" dev-profile-stylelint-fix a.css || fail "stylelint: failed"
	expect_call "stylelint|${repo}|--fix --allow-empty-input a.css" "stylelint"
	STUB_EXIT=78 run_wrapper "$repo" dev-profile-stylelint-fix a.css || fail "stylelint: missing config (78) must skip"
}

fixture_perltidy() {
	local repo
	repo="$(new_repo perltidy)"
	echo 'print 1;' >"${repo}/a.pl"
	run_wrapper "$repo" dev-profile-perltidy-fix a.pl || fail "perltidy: failed"
	expect_call "perltidy|${repo}|-b -bext=/ -q a.pl" "perltidy"
}

fixture_clang_tidy() {
	local repo
	repo="$(new_repo clang-tidy)"
	mkdir -p "${repo}/build"
	echo 'int main(){}' >"${repo}/a.cc"
	run_wrapper "$repo" dev-profile-clang-tidy-fix a.cc || fail "clang-tidy: no database must pass"
	expect_no_call "clang-tidy without compile_commands.json"
	echo '[]' >"${repo}/build/compile_commands.json"
	run_wrapper "$repo" dev-profile-clang-tidy-fix a.cc || fail "clang-tidy: failed"
	expect_call "clang-tidy|${repo}|-p ${repo}/build --checks=-*,modernize-* --fix --quiet ${repo}/a.cc" "clang-tidy"
}

fixture_absent_tools_skip() {
	local repo wrapper bare="${work}/bare" tool
	mkdir -p "$bare"
	for tool in env bash git dirname basename sort; do ln -sf "$(command -v "$tool")" "${bare}/${tool}"; done
	repo="$(new_repo absent)"
	echo 'x' >"${repo}/a.pl"
	touch "${repo}/Cargo.toml" "${repo}/a.rs" "${repo}/rector.php"
	for wrapper in dev-profile-perltidy-fix dev-profile-clippy-fix dev-profile-dotnet-format-fix \
		dev-profile-clang-tidy-fix dev-profile-rector-fix dev-profile-stylelint-fix; do
		(cd "$repo" && PATH="$bare" "${out}/bin/${wrapper}" a.pl a.rs) ||
			fail "${wrapper}: an absent tool must skip cleanly"
	done
}

fixture_ruff_modernize_rules
fixture_rector
fixture_clippy
fixture_dotnet
fixture_stylelint
fixture_perltidy
fixture_clang_tidy
fixture_absent_tools_skip
echo "modernizer fixture ok"
