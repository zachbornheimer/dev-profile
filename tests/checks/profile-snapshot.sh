#!/usr/bin/env bash
# The profile's own facts and snapshots hold. The `--deny-warnings` bar is an
# invariant this `pkl test` already evaluates, so it costs no second full
# evaluation of the profile. Runs from the repo root, like doctor; it reads the
# sources, not the render, so it ignores the generated dir doctor passes every job.
# Usage: profile-snapshot.sh [<generated-dir>]
set -euo pipefail
. "$(dirname "$0")/common.sh"
pkl test tests/profile.test.pkl || fail "pkl test (regenerate the snapshot with: pkl test --overwrite tests/profile.test.pkl)"
