#!/usr/bin/env bash
# go mod tidy at commit rewrites an untidy go.mod and --diff reports it; a
# module a parent go.work omits is tidied with GOWORK=off. Real go; no network.
# Usage: go-mod-tidy-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: go-mod-tidy-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL go-mod-tidy fixture: $*" >&2
	exit 1
}

new_repo() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	echo "$dir"
}

# An empty require block is what tidy removes without touching the network.
write_untidy_module() {
	printf 'module %s\n\ngo 1.27\n\nrequire ()\n' "$2" >"$1/go.mod"
	printf 'package main\n\nfunc main() {}\n' >"$1/main.go"
}

run_tidy() {
	(cd "$1" && shift && "${out}/bin/dev-profile-go-mod-tidy" "$@")
}

fixture_rewrites_and_reports() {
	local repo
	repo="$(new_repo plain)"
	write_untidy_module "$repo" fixture
	if run_tidy "$repo" --diff main.go >/dev/null 2>&1; then fail "plain: --diff passed on an untidy go.mod"; fi
	run_tidy "$repo" main.go || fail "plain: tidy failed"
	grep -q 'require ()' "${repo}/go.mod" && fail "plain: go.mod was not tidied"
	run_tidy "$repo" --diff go.mod || fail "plain: --diff failed on a tidy go.mod"
}

fixture_module_outside_go_work() {
	local repo
	repo="$(new_repo workspace)"
	mkdir -p "${repo}/a" "${repo}/tools/x"
	printf 'module fixture/a\n\ngo 1.27\n' >"${repo}/a/go.mod"
	printf 'package a\n' >"${repo}/a/a.go"
	printf 'go 1.27\n\nuse ./a\n' >"${repo}/go.work"
	write_untidy_module "${repo}/tools/x" fixture/x
	run_tidy "$repo" tools/x/main.go || fail "workspace: tidy failed for a module go.work omits"
	grep -q 'require ()' "${repo}/tools/x/go.mod" && fail "workspace: module outside go.work was not tidied"
	return 0
}

fixture_rewrites_and_reports
fixture_module_outside_go_work
echo "go-mod-tidy fixture ok"
