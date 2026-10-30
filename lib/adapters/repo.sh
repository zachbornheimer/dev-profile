#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/repo.sh: `mise run generate` copies it into bin/ as dev-profile-contract-repo.
# Contract adapter: repo. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-repo <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

# A contract task that does not resolve here is a doctor failure.
require_task() {
	if ! mise tasks info "$1" >/dev/null 2>&1; then
		echo "doctor: task '$1' does not resolve" >&2
		failed=1
	fi
}

# Tasks defined in this repo (mise.toml or mise-tasks/) run tools directly:
# never make, and Python only through uv (the commit fixer rewrites bare
# python3; this catches anything committed past it). Profile tasks are exempt.
repo_task_runners() {
	local make_word="(^|[^[:alnum:]_./-])make([^[:alnum:]_-]|$)|[$][({]MAKE[)}]"
	# Command position only (line start, after ; & | ( or $( and env assignments).
	local cmd="(^|[;&|(]|[$][(])[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*"
	local python_word="${cmd}(python3?|pip3?|pipx|poetry|virtualenv)([[:space:]]|$)"
	local name body file
	while IFS= read -r task_json; do
		name="$(jq -r '.name' <<<"${task_json}")"
		body="$(jq -r '(.run // []) | map(tostring) | join("\n")' <<<"${task_json}")"
		file="$(jq -r '.file // empty' <<<"${task_json}")"
		if [[ -n "${file}" && -f "${file}" ]]; then body+=$'\n'"$(cat "${file}")"; fi
		if grep -qE -e "${make_word}" <<<"${body}"; then
			echo "doctor: no-make: task '${name}' invokes make" >&2
			failed=1
		fi
		if grep -qE -e "${python_word}" <<<"${body}"; then
			echo "doctor: uv-only: task '${name}' runs python/pip/pipx/poetry/virtualenv directly; use uv run (the commit hook rewrites python3)" >&2
			failed=1
		fi
	done < <(mise tasks --json | jq -c --arg root "${PWD}/" '.[] | select(.source | startswith($root))')
}

# Secrets in the tracked tree at HEAD. A plain directory scan would also read
# gitignored local files such as .env, which never leave this machine.
scan_tree() {
	local tree
	git rev-parse -q --verify HEAD >/dev/null || nothing_to_do
	tree="$(mktemp -d)"
	git archive HEAD | tar -x -C "${tree}"
	step gitleaks dir --redact --no-banner "${tree}"
	rm -rf "${tree}"
}

doctor() {
	local task tasks
	read -ra tasks <<<"${PROFILE_CONTRACT_VERBS:?} ci"
	for task in "${tasks[@]}"; do
		require_task "${task}"
	done
	repo_task_runners
	if [[ ! -s README.md ]]; then
		echo "doctor: README.md is missing or empty" >&2
		failed=1
	fi
	step dev-profile-suppressions --tree
	step dev-profile-owned-files
	step dev-profile-retire-legacy-hooks --check
}

case "${verb}" in
setup)
	step mise install
	step mise deps install
	;;
# hk owns format checks and static analysis for every language.
lint)
	step dev-profile-hk check --all --slow --profile "${PROFILE_LINT_PROFILE:?}"
	step dev-profile-suppressions --tree
	;;
# dprint finds the Personal ancestor config from the invoking directory.
fmt) step dprint fmt ;;
scan) scan_tree ;;
doctor) doctor ;;
*) nothing_to_do ;;
esac
finish
