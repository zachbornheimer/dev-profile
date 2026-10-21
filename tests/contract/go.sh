#!/usr/bin/env bash
# Contract fixtures for Go: module discovery, go.work membership, and go fix.
# Usage: go.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' output=''
. "$(dirname "$0")/world.sh" "$@"

# A `go fix -diff` block for one file: "<path> (old|new)" headers, one-line hunk.
go_fix_block() {
	printf -- '--- %s (old)\n+++ %s (new)\n@@ -1,3 +1,3 @@\n package pkg\n \n-%s\n+%s\n' "$1" "$1" "$2" "$3"
}

# A Go repo whose package pkg has a staged a.go and an untracked b.go.
new_go_repo() {
	local repo
	repo="$(new_repo "$1")"
	mkdir -p "${repo}/pkg"
	echo "module m" >"${repo}/go.mod"
	printf 'package pkg\n\nvar A interface{}\n' >"${repo}/pkg/a.go"
	printf 'package pkg\n\nvar B interface{}\n' >"${repo}/pkg/b.go"
	git -C "$repo" add go.mod pkg/a.go
	echo "$repo"
}

fixture_go_modernize_staged_only() {
	local repo diff="${work}/go-fix-staged.diff"
	repo="$(new_go_repo go-modernize)"
	{
		go_fix_block "${repo}/pkg/a.go" "var A interface{}" "var A any"
		go_fix_block "${repo}/pkg/b.go" "var B interface{}" "var B any"
	} >"$diff"
	GO_FIX_DIFF="$diff" run_hook "$repo" pre-commit --staged || fail "go modernize: pre-commit failed"
	grep -qxF "var A any" "${repo}/pkg/a.go" || fail "go modernize: staged a.go was not modernized"
	grep -qxF "var B interface{}" "${repo}/pkg/b.go" || fail "go modernize: unstaged b.go was rewritten"
	git -C "$repo" diff --cached | grep -qxF "+var A any" || fail "go modernize: fix was not staged"
}

# Go before 1.27 has no `go fix -diff`. The fixer must stay silent and apply nothing.
fixture_go_modernize_old_go_without_diff() {
	local repo
	repo="$(new_go_repo go-modernize-no-diff)"
	GO_FIX_NO_DIFF=1 run_hook "$repo" pre-commit --staged || fail "go modernize old go: pre-commit failed"
	grep -qxF "var A interface{}" "${repo}/pkg/a.go" || fail "go modernize old go: a.go was rewritten"
	if grep -qF "flag provided but not defined" "$output"; then
		fail "go modernize old go: unknown -diff leaked to output"
	fi
	repo="$(new_go_repo go-modernize-diff-wins)"
	{
		go_fix_block "${repo}/pkg/a.go" "var A interface{}" "var A any"
		go_fix_block "${repo}/pkg/b.go" "var B interface{}" "var B any"
	} >"${work}/go-fix-wins.diff"
	GO_FIX_NO_DIFF=1 GO_FIX_DIFF="${work}/go-fix-wins.diff" run_hook "$repo" pre-commit --staged ||
		fail "go modernize: GO_FIX_DIFF must win over GO_FIX_NO_DIFF"
	grep -qxF "var A any" "${repo}/pkg/a.go" || fail "go modernize: GO_FIX_DIFF did not apply"
}

fixture_go_work() {
	local repo
	repo="$(new_repo go-work)"
	mkdir -p "${repo}/a" "${repo}/b" "${repo}/a/testdata/x"
	printf 'go 1.27\n\nuse (\n\t./a\n\t./b\n)\n' >"${repo}/go.work"
	echo "module a" >"${repo}/a/go.mod"
	echo "module b" >"${repo}/b/go.mod"
	echo "module x" >"${repo}/a/testdata/x/go.mod"
	# From a subdirectory: the dispatcher must still run at the repo root.
	run_task "${repo}/a" test || fail "go.work: test failed"
	expect_call "go|${repo}/a|test ./..." "go.work"
	expect_call "go|${repo}/b|test ./..." "go.work"
	expect_no_call "testdata/x|test" "go.work"
	expect_output "ok    go test" "go.work"
}

fixture_go_outside_workspace() {
	local repo
	repo="$(new_repo go-outside)"
	mkdir -p "${repo}/a" "${repo}/tools/x"
	printf 'go 1.27\n\nuse ./a\n' >"${repo}/go.work"
	echo "module a" >"${repo}/a/go.mod"
	echo "module x" >"${repo}/tools/x/go.mod"
	# The go stub prints nothing for `go work edit -json`; answer it with a real list.
	printf '{"Use":[{"DiskPath":"./a"}]}\n' >"${work}/go-work.json"
	GO_WORK_JSON="${work}/go-work.json" run_task "$repo" test || fail "go outside: test failed"
	expect_output "+ cd tools/x (GOWORK=off)" "go outside"
	if grep -qF "+ cd a (GOWORK=off)" "$output"; then fail "go outside: workspace member ran with GOWORK=off"; fi
}

fixture_go_modernize_staged_only
fixture_go_modernize_old_go_without_diff
fixture_go_work
fixture_go_outside_workspace
echo "contract go fixtures ok"
