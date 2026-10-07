#!/usr/bin/env bash
# go fix at pre-commit: modernizes staged Go files only, and a rewrite that
# breaks go vet blocks the commit. Real go and git; no stubs.
# Usage: go-fix-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: go-fix-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL go-fix fixture: $*" >&2
	exit 1
}

new_module() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	printf 'module fixture\n\ngo 1.27\n' >"${dir}/go.mod"
	echo "$dir"
}

# Commit hooks are off; run the wrapper exactly as the hk step does.
run_go_fix() {
	(cd "$1" && shift && "${out}/bin/dev-profile-go-fix" "$@")
}

write_old_style() {
	cat >"$1" <<'GO'
package fixture

func Max(xs []int) int {
	m := xs[0]
	for _, x := range xs {
		if x > m {
			m = x
		}
	}
	return m
}

var _ = interface{}(nil)
GO
}

fixture_rewrites_staged_file_only() {
	local repo
	repo="$(new_module modernize)"
	write_old_style "${repo}/staged.go"
	write_old_style "${repo}/untouched.go"
	sed -i.bak 's/Max/Other/' "${repo}/untouched.go" && rm "${repo}/untouched.go.bak"
	cp "${repo}/untouched.go" "${work}/untouched.before"
	run_go_fix "$repo" staged.go || fail "modernize: wrapper failed"
	grep -q 'interface{}' "${repo}/staged.go" && fail "modernize: staged file was not rewritten (still interface{})"
	cmp -s "${repo}/untouched.go" "${work}/untouched.before" || fail "modernize: unstaged file in the same package was rewritten"
}

fixture_blocks_asType_on_non_error() {
	local repo
	repo="$(new_module astype)"
	cat >"${repo}/bad.go" <<'GO'
package fixture

import "errors"

type statusCoder interface{ Code() int }

func Code(err error) int {
	var sc statusCoder
	if errors.As(err, &sc) {
		return sc.Code()
	}
	return 0
}
GO
	cp "${repo}/bad.go" "${work}/bad.before"
	if run_go_fix "$repo" bad.go 2>"${work}/stderr"; then fail "astype: broken rewrite did not block the commit"; fi
	cmp -s "${repo}/bad.go" "${work}/bad.before" || fail "astype: broken rewrite was left in the file"
	grep -q 'go vet' "${work}/stderr" || fail "astype: no explanation on stderr"
}

fixture_rewrites_staged_file_only
fixture_blocks_asType_on_non_error
echo "go-fix fixture ok"
