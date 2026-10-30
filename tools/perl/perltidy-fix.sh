#!/usr/bin/env bash
set -euo pipefail
# Edit tools/perl/perltidy-fix.sh: `mise run generate` copies it into bin/.

# shellcheck source=lib/sh/perl-tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/perl-tools.sh"
# perltidy in place with the profile's (or the repo's own) style.
(($#)) || exit 0
require_perl_tool perltidy
exec perltidy --profile="$(perl_config perltidy .)" -b -bext='/' -q "$@"
