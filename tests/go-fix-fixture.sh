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

# A go whose `fix` leaves an undefined identifier behind, as a faulty analyzer
# would: no real analyzer is guaranteed to break code on a given Go release.
fixture_blocks_rewrite_that_breaks_vet() {
	local repo shim="${work}/broken-fix-shim" real_go
	real_go="$(command -v go)"
	mkdir -p "$shim"
	cat >"${shim}/go" <<EOF
#!/usr/bin/env bash
if [[ "\${1:-}" != fix ]]; then exec "${real_go}" "\$@"; fi
"${real_go}" "\$@"
for file in ./*.go; do echo 'var _ = brokenByFix' >>"\${file}"; done
EOF
	chmod +x "${shim}/go"
	repo="$(new_module broken-fix)"
	write_old_style "${repo}/bad.go"
	cp "${repo}/bad.go" "${work}/bad.before"
	if PATH="${shim}:${PATH}" run_go_fix "$repo" bad.go 2>"${work}/stderr"; then fail "broken rewrite did not block the commit"; fi
	cmp -s "${repo}/bad.go" "${work}/bad.before" || fail "broken rewrite was left in the file"
	grep -q 'go vet' "${work}/stderr" || fail "no explanation on stderr"
}
fixture_modernizes_module_outside_go_work() {
	local repo
	repo="$(new_module workspace)"
	mkdir -p "${repo}/a" "${repo}/tools/x"
	printf 'module fixture/a\n\ngo 1.27\n' >"${repo}/a/go.mod"
	printf 'module fixture/x\n\ngo 1.27\n' >"${repo}/tools/x/go.mod"
	printf 'package a\n' >"${repo}/a/a.go"
	printf 'go 1.27\n\nuse ./a\n' >"${repo}/go.work"
	write_old_style "${repo}/tools/x/x.go"
	run_go_fix "$repo" tools/x/x.go || fail "workspace: wrapper failed"
	! grep -q 'interface{}' "${repo}/tools/x/x.go" || fail "workspace: module outside go.work was not modernized"
}

fixture_rewrites_staged_file_only
fixture_blocks_rewrite_that_breaks_vet
fixture_modernizes_module_outside_go_work
echo "go-fix fixture ok"
