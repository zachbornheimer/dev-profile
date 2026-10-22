#!/usr/bin/env bash
# The generated dprint, worktrunk and golangci configs load in the tool that
# consumes each. Usage: consumer-configs.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/common.sh"
out="${1:?usage: consumer-configs.sh <generated-dir>}"
dprint output-resolved-config --config "$out/dprint.jsonc" >/dev/null || fail dprint.jsonc
wt --config "$out/worktrunk.toml" config show >/dev/null || fail worktrunk.toml
for alias in up pr pr-draft pr-auto "done"; do
	wt --config "$out/worktrunk.toml" config alias show "$alias" >/dev/null || fail "worktrunk alias $alias"
done
wt --config "$out/worktrunk.toml" config alias dry-run pr -- @ >/dev/null || fail worktrunk alias dry-run pr
golangci-lint config verify --config "$out/golangci.yml" || fail golangci.yml
grep -F "allow-parallel-runners: true" "$out/golangci.yml" || fail "golangci allow-parallel-runners"
