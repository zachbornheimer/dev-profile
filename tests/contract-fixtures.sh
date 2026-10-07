#!/usr/bin/env bash
# Contract fixtures: run the generated root overlay against throwaway repos with
# stubbed package managers. No network. Usage: contract-fixtures.sh <generated-dir>
set -euo pipefail

out="${1:?usage: contract-fixtures.sh <generated-dir>}"
profile="$(cd "$(dirname "$0")/.." && pwd)/profile.pkl"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

root="${work}/root"
stubs="${work}/stubs"
log="${work}/calls.log"
output="${work}/output.txt"
stubbed_tools=(go golangci-lint govulncheck pnpm npm composer aube uv oxlint gitleaks)

mkdir -p "$root" "$stubs" "${work}/mise-config"
cp "${out}/personal-overlay.toml" "${root}/mise.toml"

# Each stub logs "name|dir|args" and fails when its name is in STUB_FAIL.
cat >"${stubs}/stub" <<'EOF'
#!/usr/bin/env bash
name="${0##*/}"
echo "${name}|${PWD}|$*" >>"${STUB_LOG}"
if [[ "${name} $*" == "go work edit -json" && -n "${GO_WORK_JSON:-}" ]]; then cat "${GO_WORK_JSON}"; fi
[[ " ${STUB_FAIL} " != *" ${name} "* ]]
EOF
chmod +x "${stubs}/stub"
for tool in "${stubbed_tools[@]}"; do ln -s stub "${stubs}/${tool}"; done

# Isolated from the user's global mise config; HK=0 skips global git hooks.
export STUB_LOG="$log" STUB_FAIL="" HK=0
export MISE_CONFIG_DIR="${work}/mise-config" MISE_TRUSTED_CONFIG_PATHS="$root" MISE_YES=1
export PATH="${stubs}:${out}/bin:${PATH}"

fail() {
	echo "FAIL contract fixture: $*" >&2
	[[ ! -f "$output" ]] || sed 's/^/  | /' "$output" >&2
	exit 1
}

new_repo() {
	local dir="${root}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	echo "# $1" >"${dir}/README.md"
	echo "$dir"
}

commit_all() {
	git -C "$1" add -A
	git -C "$1" -c user.name=fixture -c user.email=fixture@example.invalid \
		-c commit.gpgsign=false commit -qm "test: fixture"
}

# Run a mise task in a directory with a fresh call log; returns the task's status.
run_task() {
	: >"$log"
	(cd "$1" && mise run "$2") >"$output" 2>&1
}

expect_call() { grep -qxF -- "$1" "$log" || fail "$2: expected call '$1'"; }
expect_no_call() { ! grep -qF -- "$1" "$log" || fail "$2: unexpected call '$1'"; }
expect_output() { grep -qF -- "$1" "$output" || fail "$2: expected output '$1'"; }

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

fixture_pnpm() {
	local with without
	with="$(new_repo pnpm-with-test)"
	touch "${with}/pnpm-lock.yaml"
	echo '{"scripts":{"test":"vitest"}}' >"${with}/package.json"
	run_task "$with" test || fail "pnpm with test: test failed"
	expect_call "aube|${with}|run test" "pnpm lockfile runs through aube"

	without="$(new_repo pnpm-without-test)"
	touch "${without}/pnpm-lock.yaml"
	echo '{"scripts":{"build":"tsc"}}' >"${without}/package.json"
	run_task "$without" test || fail "pnpm without test: test should pass"
	expect_no_call "run test" "pnpm without test"
	expect_output "nothing to test" "pnpm without test"
}

fixture_composer() {
	local repo
	repo="$(new_repo composer)"
	echo '{"scripts":{"test":"phpunit"}}' >"${repo}/composer.json"
	run_task "$repo" test || fail "composer: test failed"
	expect_call "composer|${repo}|run-script test" "composer"
	commit_all "$repo"
	run_task "$repo" scan || fail "composer: scan failed"
	expect_call "composer|${repo}|audit" "composer"
	grep -qF "gitleaks|${repo}|dir --redact --no-banner " "$log" ||
		fail "composer: expected a gitleaks scan of the tracked tree"
}

fixture_no_ecosystem() {
	local repo
	repo="$(new_repo no-ecosystem)"
	run_task "$repo" test || fail "no ecosystem: test should pass"
	expect_output "nothing to test" "no ecosystem"
	run_task "$repo" build || fail "no ecosystem: build should pass"
	expect_output "nothing to build" "no ecosystem"
}

fixture_override_and_extend() {
	local override extend
	override="$(new_repo override)"
	echo "module o" >"${override}/go.mod"
	printf '[tasks.test]\nrun = "echo repo-override"\n' >"${override}/mise.toml"
	run_task "$override" test || fail "override: test failed"
	expect_output "repo-override" "override"
	expect_no_call "test ./..." "override"

	extend="$(new_repo extend)"
	echo "module e" >"${extend}/go.mod"
	printf '[tasks.test]\ndepends = ["profile:test"]\nrun = "echo repo-extend"\n' >"${extend}/mise.toml"
	run_task "$extend" test || fail "extend: test failed"
	expect_output "repo-extend" "extend"
	expect_call "go|${extend}|test ./..." "extend"
}

fixture_failure_runs_every_adapter() {
	local repo
	repo="$(new_repo failure)"
	echo "module f" >"${repo}/go.mod"
	touch "${repo}/pnpm-lock.yaml"
	echo '{"scripts":{"test":"vitest"}}' >"${repo}/package.json"
	if STUB_FAIL=go run_task "$repo" test; then fail "failure: test should fail"; fi
	expect_output "FAIL  go test" "failure"
	expect_call "aube|${repo}|run test" "failure"
}

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

fixture_repo_task_runners() {
	local clean dirty
	clean="$(new_repo runners-clean)"
	printf '[tasks.cmake-build]\nrun = "cmake --build build"\n[tasks.smoke]\nrun = "uv run scripts/smoke.py"\n[tasks."conformance:python"]\nrun = "mise run conformance:_run python"\n[tasks.pytest]\nrun = "uv run pytest -q"\n' >"${clean}/mise.toml"
	run_task "$clean" doctor || fail "runners clean: doctor should pass"

	dirty="$(new_repo runners-dirty)"
	printf '[tasks.build]\nrun = "make build"\n[tasks.smoke]\nrun = "PYTHONPATH=src python3 -m pip install -e ."\n[tasks.report]\nrun = "python3 scripts/report.py"\n' >"${dirty}/mise.toml"
	mkdir -p "${dirty}/mise-tasks"
	printf '#!/usr/bin/env bash\npip install requests\n' >"${dirty}/mise-tasks/deps"
	chmod +x "${dirty}/mise-tasks/deps"
	if run_task "$dirty" doctor; then fail "runners dirty: doctor should fail"; fi
	expect_output "no-make: task 'build' invokes make" "runners dirty"
	expect_output "uv-only: task 'smoke' runs python" "runners dirty"
	expect_output "uv-only: task 'deps' runs python" "runners dirty"
	expect_output "uv-only: task 'report' runs python" "runners dirty"
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

fixture_uv_instead_of_python_in_tasks() {
	local file="${work}/python-fix.toml" want="${work}/python-fix.want"
	cat >"$file" <<'EOF'
[tasks.a]
run = "python3 scripts/a.py --flag"
[tasks.b]
run = "PYTHONPATH=src python scripts/b.py"
[tasks.c]
run = ["uv run tools/c.py", "uv run --script d.py && python3 e.py"]
[tasks.keep]
run = ["python3 -c 'print(1)'", "uv run pytest -q", "python3 -m http.server", "mise run conformance:_run python"]
EOF
	cat >"$want" <<'EOF'
[tasks.a]
run = "uv run scripts/a.py --flag"
[tasks.b]
run = "PYTHONPATH=src uv run scripts/b.py"
[tasks.c]
run = ["uv run tools/c.py", "uv run --script d.py && uv run e.py"]
[tasks.keep]
run = ["uv run python3 -c 'print(1)'", "uv run pytest -q", "uv run python3 -m http.server", "mise run conformance:_run python"]
EOF
	dev-profile-uv-instead-of-python-in-tasks "$file"
	diff -u "$want" "$file" >"$output" || fail "uv-instead-of-python-in-tasks: unexpected rewrite"
}

fixture_go_work
fixture_go_outside_workspace
fixture_uv_instead_of_python_in_tasks
fixture_repo_task_runners
fixture_pnpm
fixture_composer
fixture_no_ecosystem
fixture_override_and_extend
fixture_failure_runs_every_adapter
fixture_suppressions
echo "contract fixtures ok"
