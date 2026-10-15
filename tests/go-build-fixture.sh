#!/usr/bin/env bash
# Go `build` writes one binary per main package into .bin/; `dev` hands the one
# default dev command to dev-profile-dev. Real go, stub dev-profile-dev; no network.
# Usage: go-build-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: go-build-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

dev_log="${work}/dev.log"
output="${work}/output.txt"
stubs="${work}/stubs"
mkdir -p "$stubs"
printf '#!/usr/bin/env bash\necho "dev-profile-dev $*" >>"%s"\n' "$dev_log" >"${stubs}/dev-profile-dev"
chmod +x "${stubs}/dev-profile-dev"

export GOTOOLCHAIN=local
export PATH="${stubs}:${out}/bin:${PATH}"
unset GOWORK

fail() {
	echo "FAIL go-build fixture: $*" >&2
	[[ ! -f "$output" ]] || sed 's/^/  | /' "$output" >&2
	exit 1
}

new_repo() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	echo "$dir"
}

# write_main <dir>: a main package in <dir>.
write_main() {
	mkdir -p "$1"
	printf 'package main\n\nfunc main() {}\n' >"$1/main.go"
}

write_module() {
	printf 'module %s\n\ngo 1.27\n' "$2" >"$1/go.mod"
}

# Run a contract adapter from a directory; dev-profile-dev is the stub.
run_adapter() {
	local repo="$1" adapter="$2" verb="$3"
	: >"$dev_log"
	(cd "$repo" && "${out}/bin/dev-profile-contract-${adapter}" "$verb") >"$output" 2>&1
}

expect_file() { [[ -x "$1" ]] || fail "$2: expected executable $1"; }
expect_output() { grep -qF -- "$1" "$output" || fail "$2: expected output '$1'"; }

fixture_every_main_package_gets_a_binary() {
	local repo
	repo="$(new_repo multi-main)"
	write_module "$repo" example.com/team/tools
	write_main "${repo}/cmd/alpha"
	write_main "${repo}/cmd/beta"
	mkdir -p "${repo}/lib"
	printf 'package lib\n' >"${repo}/lib/lib.go"
	run_adapter "$repo" go build || fail "multi-main: build failed"
	expect_file "${repo}/.bin/alpha" "multi-main"
	expect_file "${repo}/.bin/beta" "multi-main"
	[[ ! -e "${repo}/.bin/lib" ]] || fail "multi-main: a non-main package produced a binary"
}

fixture_module_root_binary_is_named_for_the_module() {
	local repo
	repo="$(new_repo root-main)"
	write_module "$repo" example.com/team/rootapp/v2
	write_main "$repo"
	run_adapter "$repo" go build || fail "root main: build failed"
	expect_file "${repo}/.bin/rootapp" "root main (the /v2 suffix is not a name)"
}

fixture_module_without_main_is_only_compiled() {
	local repo
	repo="$(new_repo library)"
	write_module "$repo" example.com/team/library
	printf 'package library\n' >"${repo}/library.go"
	run_adapter "$repo" go build || fail "library: build failed"
	[[ ! -e "${repo}/.bin" ]] || fail "library: .bin was created for a module with no main package"
	printf 'package library\n\nvar broken = missing\n' >"${repo}/library.go"
	if run_adapter "$repo" go build; then fail "library: a compile error must fail the build"; fi
}

fixture_workspace_modules_share_one_bin() {
	local repo
	repo="$(new_repo workspace)"
	mkdir -p "${repo}/a" "${repo}/b"
	write_module "${repo}/a" example.com/a
	write_module "${repo}/b" example.com/b
	write_main "${repo}/a/cmd/first"
	write_main "${repo}/b/cmd/second"
	printf 'go 1.27\n\nuse (\n\t./a\n\t./b\n)\n' >"${repo}/go.work"
	run_adapter "$repo" go build || fail "workspace: build failed"
	expect_file "${repo}/.bin/first" "workspace"
	expect_file "${repo}/.bin/second" "workspace"
}

fixture_two_mains_with_one_name_fail() {
	local repo
	repo="$(new_repo name-clash)"
	write_module "$repo" example.com/clash
	write_main "${repo}/cmd/one/tool"
	write_main "${repo}/cmd/two/tool"
	if run_adapter "$repo" go build; then fail "name clash: build should fail"; fi
	expect_output "would overwrite .bin/tool" "name clash"
}

fixture_dev_runs_the_one_main_behind_the_proxy() {
	local repo
	repo="$(new_repo dev-one)"
	write_module "$repo" example.com/one
	write_main "${repo}/cmd/server"
	run_adapter "$repo" go dev || fail "dev one: failed"
	grep -qxF "dev-profile-dev -- go run example.com/one/cmd/server" "$dev_log" || fail "dev one: the wrapper was not given the main package"
}

fixture_dev_with_several_mains_lists_them() {
	local repo
	repo="$(new_repo dev-many)"
	write_module "$repo" example.com/many
	write_main "${repo}/cmd/api"
	write_main "${repo}/cmd/worker"
	if run_adapter "$repo" go dev; then fail "dev many: should fail with several main packages"; fi
	expect_output "go run example.com/many/cmd/api" "dev many"
	expect_output "go run example.com/many/cmd/worker" "dev many"
	[[ ! -s "$dev_log" ]] || fail "dev many: something started anyway"
}

fixture_dev_without_main_has_nothing_to_do() {
	local repo code=0
	repo="$(new_repo dev-none)"
	write_module "$repo" example.com/none
	printf 'package none\n' >"${repo}/none.go"
	run_adapter "$repo" go dev || code=$?
	[[ "$code" -eq 3 ]] || fail "dev none: expected the nothing-to-do exit 3, got ${code}"
}

fixture_node_dev_runs_the_package_dev_script_behind_the_proxy() {
	local repo
	repo="$(new_repo node-dev)"
	printf '{"scripts":{"dev":"vite"}}\n' >"${repo}/package.json"
	: >"${repo}/package-lock.json"
	run_adapter "$repo" node dev || fail "node dev: failed"
	grep -qxF "dev-profile-dev -- aube run dev" "$dev_log" || fail "node dev: the wrapper was not given the package dev script"
}

fixture_compose_dev_runs_compose_up() {
	local repo
	repo="$(new_repo compose-dev)"
	printf 'services: {}\n' >"${repo}/compose.yaml"
	run_adapter "$repo" compose dev || fail "compose dev: failed"
	grep -qxF "dev-profile-dev -- docker compose up" "$dev_log" || fail "compose dev: wrong command"
}

# The dev verb starts exactly one default; the dispatcher refuses none or several.
run_dispatcher_dev() {
	: >"$dev_log"
	(cd "$1" && "${out}/bin/dev-profile-contract" dev) >"$output" 2>&1
}

fixture_dispatcher_dev_picks_the_only_default() {
	local repo
	repo="$(new_repo dispatch-one)"
	write_module "$repo" example.com/one
	write_main "${repo}/cmd/server"
	run_dispatcher_dev "$repo" || fail "dispatch one: failed"
	grep -qxF "dev-profile-dev -- go run example.com/one/cmd/server" "$dev_log" || fail "dispatch one: the default did not run"
}

fixture_dispatcher_dev_refuses_several_defaults() {
	local repo
	repo="$(new_repo dispatch-two)"
	write_module "$repo" example.com/two
	write_main "${repo}/cmd/server"
	printf 'services: {}\n' >"${repo}/compose.yaml"
	if run_dispatcher_dev "$repo"; then fail "dispatch two: a Go main plus compose is ambiguous"; fi
	expect_output "2 default dev commands" "dispatch two"
	expect_output "go run example.com/two/cmd/server" "dispatch two"
	expect_output "docker compose up" "dispatch two"
	[[ ! -s "$dev_log" ]] || fail "dispatch two: something started anyway"
}

fixture_dispatcher_dev_without_default_says_what_to_define() {
	local repo
	repo="$(new_repo dispatch-none)"
	write_module "$repo" example.com/none
	printf 'package none\n' >"${repo}/none.go"
	if run_dispatcher_dev "$repo"; then fail "dispatch none: should fail without a default"; fi
	expect_output "Define a repo 'dev' task" "dispatch none"
}

fixture_every_main_package_gets_a_binary
fixture_module_root_binary_is_named_for_the_module
fixture_module_without_main_is_only_compiled
fixture_workspace_modules_share_one_bin
fixture_two_mains_with_one_name_fail
fixture_dev_runs_the_one_main_behind_the_proxy
fixture_dev_with_several_mains_lists_them
fixture_dev_without_main_has_nothing_to_do
fixture_node_dev_runs_the_package_dev_script_behind_the_proxy
fixture_compose_dev_runs_compose_up
fixture_dispatcher_dev_picks_the_only_default
fixture_dispatcher_dev_refuses_several_defaults
fixture_dispatcher_dev_without_default_says_what_to_define
echo "go-build fixture ok"
