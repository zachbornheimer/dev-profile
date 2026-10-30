#!/usr/bin/env bash
set -euo pipefail
# Edit tools/perl/perltidy-format.sh: `mise run generate` copies it into bin/.

# shellcheck source=lib/sh/perl-tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/perl-tools.sh"
# The dprint exec command: perltidy on stdin, in the style of the repo holding the file at $1.
require_perl_tool perltidy
exec perltidy --profile="$(perl_config perltidy "$(dirname "${1:-.}")")" -q
