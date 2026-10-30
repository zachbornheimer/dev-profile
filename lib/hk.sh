#!/usr/bin/env bash
set -euo pipefail
# Edit lib/hk.sh: `mise run generate` copies it into bin/.
# hk 2.5.0 reads its user config only from $XDG_CONFIG_HOME/hk (HK_CONFIG_DIR is
# ignored), so this points that at the render for hk alone. Everything else keeps
# its own config home, mise's included.

# Run hk with the rendered profile's config, never the machine's ~/.config/hk.
render_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export MISE_CONFIG_DIR="${MISE_CONFIG_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/mise}"
export XDG_CONFIG_HOME="${render_dir}/xdg"
exec hk "$@"
