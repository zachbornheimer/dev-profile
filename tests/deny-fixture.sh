#!/usr/bin/env bash
# The shared deny.toml: cargo-deny finds it by parent-directory lookup from a repo
# under the code root, and its license allow-list judges the repo. Real cargo-deny
# and cargo, offline (a dependency-free crate; the advisory db is not consulted).
# Usage: deny-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: deny-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL deny fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# A dependency-free crate under a code root that carries only the generated deny.toml.
new_crate() { # <name> <license>
	local dir="${work}/root/$1"
	mkdir -p "${dir}/src"
	printf '[package]\nname = "%s"\nversion = "0.1.0"\nedition = "2024"\nlicense = "%s"\n' "$1" "$2" >"${dir}/Cargo.toml"
	echo 'fn main() {}' >"${dir}/src/main.rs"
	(cd "$dir" && cargo generate-lockfile --offline) >"${work}/output.txt" 2>&1 || fail "$1: could not lock the crate"
	echo "$dir"
}

check_licenses() { # <crate dir>; the verb hk runs, narrowed to the offline checks
	(cd "$1" && cargo-deny --locked --workspace check licenses bans sources) >"${work}/output.txt" 2>&1
}

mkdir -p "${work}/root"
cat "${out}/deny.toml" >"${work}/root/deny.toml"

permissive="$(new_crate permissive "MIT OR Apache-2.0")"
check_licenses "$permissive" || fail "a permissive crate must pass through the root deny.toml"

copyleft="$(new_crate copyleft "GPL-3.0-only")"
if check_licenses "$copyleft"; then fail "a copyleft crate must be rejected by the root deny.toml"; fi
grep -qF "not explicitly allowed" "${work}/output.txt" || fail "copyleft crate failed for a reason other than the allow-list"

echo "deny fixture ok"
