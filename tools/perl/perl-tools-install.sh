#!/usr/bin/env bash
set -euo pipefail
# Edit tools/perl/perl-tools-install.sh: `mise run generate` copies it into bin/.
# shellcheck source=lib/sh/perl-tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/perl-tools.sh"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"
# Install what is missing; repeat runs change nothing.
if command -v perltidy >/dev/null 2>&1 && command -v perlcritic >/dev/null 2>&1; then exit 0; fi
exec mise exec "perl@${PROFILE_PERL_VERSION:?}" -- cpanm --quiet --notest --local-lib "${perl_lib_root}" Perl::Tidy Perl::Critic
