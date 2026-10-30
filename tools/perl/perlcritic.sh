#!/usr/bin/env bash
set -euo pipefail
# Edit tools/perl/perlcritic.sh: `mise run generate` copies it into bin/.

# shellcheck source=lib/sh/perl-tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/perl-tools.sh"
# perlcritic with the profile's (or the repo's own) policy set.
(($#)) || exit 0
require_perl_tool perlcritic
exec perlcritic --profile="$(perl_config perlcritic .)" "$@"
