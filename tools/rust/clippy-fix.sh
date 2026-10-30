#!/usr/bin/env bash
set -euo pipefail
# Edit tools/rust/clippy-fix.sh: `mise run generate` copies it into bin/.

# `cargo clippy --fix` rewrites whole crates and verifies each fix still builds.
# A crate with unstaged edits is left alone: the fixes would land in files this
# commit does not stage.
(($#)) || exit 0
command -v cargo >/dev/null 2>&1 || exit 0
cargo clippy --version >/dev/null 2>&1 || exit 0
# shellcheck source=lib/sh/nearest-up.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/nearest-up.sh"

for file in "$@"; do
	nearest_up "$(absolute "${file}")" Cargo.toml
done | sort -u | while IFS= read -r crate; do
	[[ -n "${crate}" ]] || continue
	if ! git diff --quiet -- "${crate}"; then
		echo "clippy-fix: skipping ${crate#"${root}/"} (unstaged changes)" >&2
		continue
	fi
	(cd "${crate}" && cargo clippy --fix --allow-dirty --allow-staged --quiet) || true
done
