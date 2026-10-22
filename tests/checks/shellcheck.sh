#!/usr/bin/env bash
# Same bar the profile sets for every repo's push: warnings block, info tips do
# not. Runs from the repo root, like doctor. Usage: shellcheck.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/common.sh"
out="${1:?usage: shellcheck.sh <generated-dir>}"
# -x follows `source`, so each scenario file is judged with its world.sh (tests/checks/*.sh with common.sh).
shellcheck -x --severity=warning "$out"/bin/* tests/*.sh tests/checks/*.sh tests/contract/*.sh tests/dev-family/*.sh tests/guards/*.sh tests/lint-binding/*.sh || fail shellcheck
