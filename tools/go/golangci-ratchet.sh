#!/usr/bin/env bash
set -euo pipefail
# Edit tools/go/golangci-ratchet.sh: `mise run generate` copies it into bin/.

# Push gate: fail only on issues the branch adds relative to the upstream default
# branch, so old debt in untouched files never blocks a push. Without a base ref
# (no remote, fresh clone) fall back to the full tree. `mise run lint` runs the full-tree twin (fullTreeCheck) instead.
base=""
for ref in "$(git symbolic-ref -q --short refs/remotes/origin/HEAD || true)" origin/main origin/master; do
	if [[ -n "${ref}" ]] && git rev-parse -q --verify "${ref}^{commit}" >/dev/null; then
		base="${ref}"
		break
	fi
done
if [[ -z "${base}" ]]; then
	echo "golangci-ratchet: no upstream default branch; linting the full tree" >&2
	exec golangci-lint run --fix=false --allow-parallel-runners ./...
fi
exec golangci-lint run --fix=false --allow-parallel-runners --new-from-merge-base="${base}" ./...
