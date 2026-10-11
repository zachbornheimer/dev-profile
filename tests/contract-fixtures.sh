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
stubbed_tools=(go goimports golangci-lint govulncheck pnpm npm composer aube uv oxlint gitleaks dotnet dprint shellcheck markdownlint betterleaks)

mkdir -p "$root" "$stubs" "${work}/mise-config" "${work}/hk-config"
cp "${out}/personal-overlay.toml" "${root}/mise.toml"
# The generated hk config, active the way bootstrap links it (HK_CONFIG_DIR/config.pkl).
ln -s "${out}/hk-config.pkl" "${work}/hk-config/config.pkl"

# Each stub logs "name|dir|args" and fails when its name is in STUB_FAIL.
cat >"${stubs}/stub" <<'EOF'
#!/usr/bin/env bash
name="${0##*/}"
echo "${name}|${PWD}|$*" >>"${STUB_LOG}"
if [[ "${name} $*" == "go work edit -json" && -n "${GO_WORK_JSON:-}" ]]; then cat "${GO_WORK_JSON}"; fi
if [[ "${name} $*" == "go fix -diff "* && -n "${GO_FIX_DIFF:-}" ]]; then cat "${GO_FIX_DIFF}"; fi
# go vet rejects a package whose files contain GO_VET_REJECTS (a fix that broke it).
if [[ "${name} ${1:-}" == "go vet" && -n "${GO_VET_REJECTS:-}" ]] && grep -rqF -- "${GO_VET_REJECTS}" .; then
	echo "vet: ${GO_VET_REJECTS} does not compile" >&2
	exit 1
fi
# go refuses a GOWORK that is neither "off" nor a go.work file.
if [[ "${name}" == "go" && -n "${GOWORK:-}" && "${GOWORK}" != "off" && ! -f "${GOWORK}" ]]; then
	echo "go: GOWORK=${GOWORK} is not a go.work file" >&2
	exit 1
fi
[[ " ${STUB_FAIL} " != *" ${name} "* ]]
EOF
chmod +x "${stubs}/stub"
for tool in "${stubbed_tools[@]}"; do ln -s stub "${stubs}/${tool}"; done

# Isolated from the user's global mise config; HK=0 skips global git hooks.
export STUB_LOG="$log" STUB_FAIL="" HK=0
export MISE_CONFIG_DIR="${work}/mise-config" MISE_TRUSTED_CONFIG_PATHS="$root" MISE_YES=1
export PATH="${stubs}:${out}/bin:${PATH}"
# Hook fixtures pick the hk config per run; never the caller's.
unset HK_CONFIG_DIR HK_FILE

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

# Run a global git hook the way git does, against the active hk config.
run_hook() {
	local repo="$1"
	shift
	: >"$log"
	(cd "$repo" && HK=1 HK_CONFIG_DIR="${HK_CONFIG_DIR:-${work}/hk-config}" dev-profile-git-hook "$@") >"$output" 2>&1
}

expect_call() { grep -qxF -- "$1" "$log" || fail "$2: expected call '$1'"; }
expect_no_call() { ! grep -qF -- "$1" "$log" || fail "$2: unexpected call '$1'"; }
expect_output() { grep -qF -- "$1" "$output" || fail "$2: expected output '$1'"; }

fixture_dotnet_targets() {
	local nested sln deep generated
	nested="$(new_repo dotnet-nested)"
	mkdir -p "${nested}/packages/csharp/src" "${nested}/packages/csharp/obj"
	touch "${nested}/packages/csharp/src/Sdk.csproj" "${nested}/packages/csharp/obj/Gen.csproj"
	run_task "$nested" test || fail "dotnet nested: test failed"
	expect_call "dotnet|${nested}|test packages/csharp/src/Sdk.csproj" "dotnet nested"
	expect_no_call "obj/Gen.csproj" "dotnet nested"

	sln="$(new_repo dotnet-sln)"
	mkdir -p "${sln}/src"
	touch "${sln}/App.sln" "${sln}/src/App.csproj"
	run_task "$sln" build || fail "dotnet sln: build failed"
	expect_call "dotnet|${sln}|build App.sln" "dotnet sln"
	expect_no_call "build src/App.csproj" "dotnet sln"

	deep="$(new_repo dotnet-deep-sln)"
	mkdir -p "${deep}/services/api"
	touch "${deep}/services/api/Api.sln"
	run_task "$deep" build || fail "dotnet deep sln: build failed"
	expect_call "dotnet|${deep}|build services/api/Api.sln" "dotnet deep sln"

	generated="$(new_repo dotnet-generated-only)"
	mkdir -p "${generated}/obj"
	touch "${generated}/obj/Gen.csproj"
	run_task "$generated" build || fail "dotnet generated-only: build should pass"
	expect_output "skip  dotnet build (nothing to build)" "dotnet generated-only"
	expect_no_call "dotnet|" "dotnet generated-only"
}

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

fixture_go_fix_that_breaks_compilation_blocks() {
	local repo diff="${work}/go-fix-broken.diff"
	repo="$(new_go_repo go-broken-fix)"
	go_fix_block "${repo}/pkg/a.go" "var A interface{}" "var A = errors.AsType[statusCoder]" >"$diff"
	if GO_FIX_DIFF="$diff" GO_VET_REJECTS="AsType" run_hook "$repo" pre-commit --staged; then
		fail "go compile guard: a fix that breaks the build must block the commit"
	fi
	expect_output "commit blocked: pkg does not build" "go compile guard"
	expect_output "staged: pkg/a.go" "go compile guard"
}

fixture_go_guard_package_patterns() {
	local repo
	# Module at the repo root, staged file in a subpackage.
	repo="$(new_go_repo go-root-module)"
	run_hook "$repo" pre-commit --staged || fail "go patterns: root module subpackage failed"
	expect_call "go|${repo}|vet ./pkg" "go patterns root module"
	# Module in a subdirectory.
	repo="$(new_repo go-sub-module)"
	mkdir -p "${repo}/svc/pkg"
	echo "module s" >"${repo}/svc/go.mod"
	printf 'package pkg\n\nvar A int\n' >"${repo}/svc/pkg/a.go"
	git -C "$repo" add svc
	run_hook "$repo" pre-commit --staged || fail "go patterns: subdirectory module failed"
	expect_call "go|${repo}/svc|vet ./pkg" "go patterns subdirectory module"
	# Staged file at the module root.
	repo="$(new_repo go-module-root-file)"
	echo "module r" >"${repo}/go.mod"
	printf 'package r\n\nvar A int\n' >"${repo}/a.go"
	git -C "$repo" add go.mod a.go
	run_hook "$repo" pre-commit --staged || fail "go patterns: module root file failed"
	expect_call "go|${repo}|vet ." "go patterns module root file"
}

fixture_git_hook_skips_undefined_hook() {
	local repo stale="${work}/stale-hk-config" msg="${work}/commit-msg.txt"
	repo="$(new_repo hook-skew)"
	mkdir -p "$stale"
	printf 'amends "%s"\nhooks { ["pre-push"] { steps { ["noop"] { check = "true" } } } }\n' \
		"package://github.com/jdx/hk/releases/download/v2.5.0/hk@2.5.0#/Config.pkl" >"${stale}/config.pkl"
	echo "feat: add thing" >"$msg"
	HK_CONFIG_DIR="$stale" run_hook "$repo" commit-msg "$msg" || fail "hook skew: an undefined hook must not fail"
	expect_output "mise bootstrap --from" "hook skew"
	echo "not conventional" >"$msg"
	if run_hook "$repo" commit-msg "$msg"; then fail "hook skew: a defined hook's failure must still block"; fi
	expect_output "subject must be" "hook skew"
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
	run_task "$repo" scan || fail "composer without lock: scan failed"
	expect_no_call "audit --locked" "composer without lock"
	echo '{}' >"${repo}/composer.lock"
	commit_all "$repo"
	run_task "$repo" scan || fail "composer: scan failed"
	expect_call "composer|${repo}|audit --locked" "composer with lock"
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
[tools]
python = "3.12"
python="3.12"
"python" = "3.12"
python3 = "3.12"
[tasks.multi]
run = """
python script.py
"""
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
[tools]
python = "3.12"
python="3.12"
"python" = "3.12"
python3 = "3.12"
[tasks.multi]
run = """
uv run script.py
"""
EOF
	dev-profile-uv-instead-of-python-in-tasks "$file"
	diff -u "$want" "$file" >"$output" || fail "uv-instead-of-python-in-tasks: unexpected rewrite"
}

fixture_nested_node_setup() {
	local repo
	repo="$(new_repo nested-node)"
	mkdir -p "${repo}/packages/ts" "${repo}/tests/runner" "${repo}/packages/ts/node_modules/dep"
	touch "${repo}/packages/ts/package-lock.json" "${repo}/tests/runner/aube-lock.yaml" \
		"${repo}/packages/ts/node_modules/dep/package-lock.json"
	echo '{}' >"${repo}/packages/ts/package.json"
	echo '{}' >"${repo}/tests/runner/package.json"
	run_task "$repo" setup || fail "nested node: setup failed"
	expect_call "aube|${repo}/packages/ts|install" "nested node"
	expect_call "aube|${repo}/tests/runner|install" "nested node"
	expect_no_call "node_modules/dep|install" "nested node"
}

fixture_go_modernize_staged_only
fixture_go_fix_that_breaks_compilation_blocks
fixture_go_guard_package_patterns
fixture_git_hook_skips_undefined_hook
# mise renders a task script through Tera only when the task runs, so `mise tasks`
# passes on a script Tera rejects (a `${#array[@]}` reads as a comment opener).
# A dry run renders every task without executing it.
# A clean repo on its default branch with an origin, the shape CI and `mise run lint` see.
new_published_default_branch_repo() {
	local repo
	repo="$(new_repo "$1")"
	git -C "$repo" checkout -q -b main
	git -C "$repo" remote add origin "https://example.invalid/${1}.git"
	commit_all "$repo"
	echo "$repo"
}

fixture_lint_ignores_commit_guards_on_default_branch() {
	local repo
	repo="$(new_published_default_branch_repo lint-on-main)"
	HK_CONFIG_DIR="${work}/hk-config" run_task "$repo" lint ||
		fail "lint on default branch: a commit-only guard failed the lint verb"
}

fixture_commit_guard_still_blocks_commit_on_default_branch() {
	local repo
	repo="$(new_published_default_branch_repo commit-on-main)"
	echo change >>"${repo}/README.md"
	git -C "$repo" add -A
	if run_hook "$repo" pre-commit --staged; then fail "commit guard: a commit on the default branch was allowed"; fi
	expect_output "protected branch" "commit guard"
}

fixture_every_task_renders() {
	local repo task
	repo="$(new_repo task-render)"
	(cd "$repo" && mise tasks ls --json | jq -r '.[].name') >"${work}/task-names.txt" ||
		fail "task render: could not list tasks"
	[[ -s "${work}/task-names.txt" ]] || fail "task render: the overlay defines no tasks"
	while IFS= read -r task; do
		(cd "$repo" && mise run -n "$task") >"$output" 2>&1 || fail "task render: '${task}' does not load"
	done <"${work}/task-names.txt"
}

# Real rustfmt. Bare rustfmt assumes edition 2015, which sorts imports differently
# from `cargo fmt` on a 2024 crate; the wrapper must agree with the crate's edition.
fixture_rustfmt_follows_crate_edition() {
	local repo
	repo="$(new_repo rust-edition)"
	mkdir -p "${repo}/src"
	printf '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2024"\n' >"${repo}/Cargo.toml"
	printf 'use std::collections::{HashMap, hash_map};\n\nfn main() {}\n' >"${repo}/src/main.rs"
	cp "${repo}/src/main.rs" "${work}/main.before"

	(cd "$work" && dev-profile-rustfmt --stdin-path "${repo}/src/main.rs" <"${work}/main.before") >"${work}/main.stdin" 2>"$output" ||
		fail "rustfmt: stdin mode failed"
	cmp -s "${work}/main.before" "${work}/main.stdin" || fail "rustfmt: stdin mode reformatted a 2024-formatted file"

	(cd "$work" && dev-profile-rustfmt "${repo}/src/main.rs") >"$output" 2>&1 || fail "rustfmt: file mode failed"
	cmp -s "${work}/main.before" "${repo}/src/main.rs" || fail "rustfmt: file mode reformatted a 2024-formatted file"
}

fixture_every_task_renders
fixture_rustfmt_follows_crate_edition
fixture_go_work
fixture_dotnet_targets
fixture_nested_node_setup
fixture_go_outside_workspace
fixture_uv_instead_of_python_in_tasks
fixture_repo_task_runners
fixture_pnpm
fixture_composer
fixture_no_ecosystem
fixture_override_and_extend
fixture_failure_runs_every_adapter
fixture_suppressions
fixture_suppressions_language_scope
fixture_suppressions_semgrep
fixture_lint_ignores_commit_guards_on_default_branch
fixture_commit_guard_still_blocks_commit_on_default_branch
echo "contract fixtures ok"
