#!/bin/sh
set -eu
# Edit lib/dprint.sh: `mise run generate` copies it into bin/ as dev-profile-dprint.
# What Neovim runs on save: the profile's dprint by absolute path. A PATH that
# predates a pin change cannot pick another build, and mise's shim (44 ms a call)
# is only the way to a pin that is not installed yet. ${0%/*}, not dirname: no fork.
# shellcheck source=/dev/null
. "${0%/*}/../lib/facts.sh"
mise_data="${MISE_DATA_DIR:-${XDG_DATA_HOME:-${HOME}/.local/share}/mise}"
pinned="${mise_data}/installs/dprint/${PROFILE_DPRINT_VERSION:?}/dprint"
[ -x "${pinned}" ] && exec "${pinned}" "$@"
[ -x "${mise_data}/shims/dprint" ] && exec "${mise_data}/shims/dprint" "$@"
exec dprint "$@"
