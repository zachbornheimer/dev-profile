#!/usr/bin/env bash
# `profile:lint` through a runner and the local entry must fail a Go printf
# mismatch. Skipped where golangci-lint or go is not installed.
# Usage: go.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/world.sh" "$@"

if command -v golangci-lint >/dev/null 2>&1 && command -v go >/dev/null 2>&1; then
	bad_go="$(new_repo bad-go)"
	printf 'module example.com/fixture\n\ngo 1.22\n' >"${bad_go}/go.mod"
	printf 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Printf("%%d\\n", "text") }\n' >"${bad_go}/main.go"
	for context in runner entry; do
		if lint "${context}" "${bad_go}"; then fail "${context}: a Go printf mismatch must fail profile:lint"; fi
	done
fi

echo "lint-binding go fixture ok"
