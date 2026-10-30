# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: go-modules.sh plus `pattern <module> <dir>`, the go package pattern for a dir.
# Edit lib/sh/go-packages.sh: `mise run generate` copies it into lib/.

# shellcheck source=lib/sh/go-modules.sh
source "$(dirname "${BASH_SOURCE[0]}")/go-modules.sh"

# The go package pattern for a package dir, relative to its module ("./x" or ".").
pattern() {
	echo ".${2#"$1"}"
}
