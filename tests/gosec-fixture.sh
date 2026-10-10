#!/usr/bin/env bash
# gosec at pre-push: fails only on findings in the pushed files, and a process
# facade (facade.go / facades.go) may run a caller-given command without
# tripping the subprocess rules. Real gosec; skips when it is not installed.
# Usage: gosec-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: gosec-fixture.sh <generated-dir>}"
command -v gosec >/dev/null 2>&1 || {
	echo "gosec fixture skipped: gosec not installed"
	exit 0
}
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL gosec fixture: $*" >&2
	exit 1
}

new_module() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q
	printf 'module fixture\n\ngo 1.27\n' >"${dir}/go.mod"
	echo "$dir"
}

run_gosec() {
	(cd "$1" && shift && "${out}/bin/dev-profile-gosec-packages" "$@")
}

# exec.Command with a variable program is G204 wherever it appears.
write_exec() {
	cat >"$1" <<GO
package $2

import (
	"context"
	"os/exec"
)

func Run(ctx context.Context, argv []string) error {
	return exec.CommandContext(ctx, argv[0], argv[1:]...).Run()
}
GO
}

fixture_facade_may_exec_a_caller_command() {
	local repo
	repo="$(new_module facade)"
	mkdir -p "${repo}/process"
	write_exec "${repo}/process/facades.go" process
	run_gosec "$repo" process/facades.go 2>"${work}/stderr" || fail "facades.go: G204 blocked the process facade: $(cat "${work}/stderr")"
}

fixture_other_files_still_flag_exec() {
	local repo
	repo="$(new_module plain)"
	mkdir -p "${repo}/runner"
	write_exec "${repo}/runner/runner.go" runner
	if run_gosec "$repo" runner/runner.go 2>"${work}/stderr"; then fail "runner.go: G204 was not reported outside a facade"; fi
	grep -q 'G204' "${work}/stderr" || fail "runner.go: expected a G204 finding, got: $(cat "${work}/stderr")"
}

# A facade is exempt from the boundary rules only; any other finding in it still fails.
fixture_facade_keeps_every_other_rule() {
	local repo
	repo="$(new_module facade-other)"
	mkdir -p "${repo}/process"
	cat >"${repo}/process/facade.go" <<'GO'
package process

import "os"

func Write(path string, data []byte) error {
	return os.WriteFile(path, data, 0o644) // G306: permissions wider than 0600
}
GO
	if run_gosec "$repo" process/facade.go 2>"${work}/stderr"; then fail "facade.go: a non-boundary finding was swallowed"; fi
	grep -q 'G306' "${work}/stderr" || fail "facade.go: expected G306, got: $(cat "${work}/stderr")"
}

# A package directory named process is the subprocess boundary; one named fs
# is the filesystem boundary. Each is exempt from its own rule only.
fixture_boundary_packages_are_exempt_from_their_own_rule() {
	local repo
	repo="$(new_module boundary)"
	mkdir -p "${repo}/internal/process" "${repo}/internal/fs"
	write_exec "${repo}/internal/process/runner.go" process
	cat >"${repo}/internal/fs/disk.go" <<'GO'
package fs

import "os"

func ReadFile(path string) ([]byte, error) { return os.ReadFile(path) }
GO
	run_gosec "$repo" internal/process/runner.go 2>"${work}/stderr" || fail "process package: G204 blocked the boundary: $(cat "${work}/stderr")"
	run_gosec "$repo" internal/fs/disk.go 2>"${work}/stderr" || fail "fs package: G304 blocked the boundary: $(cat "${work}/stderr")"
	# The fs package is not exempt from the subprocess rule.
	write_exec "${repo}/internal/fs/spawn.go" fs
	if run_gosec "$repo" internal/fs/spawn.go 2>"${work}/stderr"; then fail "fs package: G204 was swallowed"; fi
	grep -q 'G204' "${work}/stderr" || fail "fs package: expected G204, got: $(cat "${work}/stderr")"
}

fixture_facade_may_exec_a_caller_command
fixture_other_files_still_flag_exec
fixture_facade_keeps_every_other_rule
fixture_boundary_packages_are_exempt_from_their_own_rule
echo "gosec fixture ok"
