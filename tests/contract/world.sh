#!/usr/bin/env bash
# The world every contract fixture runs in, sourced by the files in this
# directory: one throwaway root, stubs for each package manager and linter a
# contract task reaches for, and the generated overlay installed the way a code
# root sees it. Each fixture file owns its world, so doctor runs them as a pool.
# Usage (sourced): . world.sh <generated-dir>
set -euo pipefail

# Sourced, never run: a fixture file that forgot to source this would otherwise
# look like a passing fixture that did nothing.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	echo 'world.sh is sourced by the fixture files in this directory; run those instead' >&2
	exit 2
fi

out="${1:?usage: <fixture>.sh <generated-dir>}"
# Exported: every fixture file and every child process reads this world.
export out profile work root stubs log output
profile="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/profile.pkl"
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
# GO_FIX_DIFF wins when both are set, so the staged-only fixture still applies.
if [[ "${name} $*" == "go fix -diff "* && -z "${GO_FIX_DIFF:-}" && -n "${GO_FIX_NO_DIFF:-}" ]]; then
	echo "flag provided but not defined: -diff" >&2
	echo "usage: go fix [-fix list] [packages]" >&2
	exit 2
fi
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
# These stubs intentionally shadow profile pins; aggressive PATH priority would
# put the real go/node/git ahead of them and test the machine instead of dispatch.
export MISE_ACTIVATE_AGGRESSIVE=0
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
