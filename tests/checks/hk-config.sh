#!/usr/bin/env bash
# hk accepts the rendered config. Its own file because it is the one check whose
# cost the pinned hk sets: `hk validate` takes over a minute and about 1.8 GB on
# hk 2.5.0, so it starts first and must not hold anything else up.
# Usage: hk-config.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/common.sh"
out="${1:?usage: hk-config.sh <generated-dir>}"
HK_FILE="$out/hk-config.pkl" hk validate >/dev/null || fail hk-config.pkl
