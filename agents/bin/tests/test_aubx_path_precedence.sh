#!/usr/bin/env bash
# Proves the aubx scope guard wins PATH in every shell this machine starts.
#
# The guard only confines a global skill install when `aubx` resolves to
# ~/.agents/bin/aubx. mise activate prepends its own install bins after the rc
# files run, so a PATH that merely *contains* ~/.agents/bin late resolves the
# raw aubx and writes into every detected harness. Each rc file must therefore
# move the directory to the front, not check for its presence.
set -uo pipefail

GUARD="$HOME/.agents/bin/aubx"
MISE_AUBX="$(ls -d "$HOME"/.local/share/mise/installs/aube/*/.mise-bins 2>/dev/null | head -1)"
[ -x "$GUARD" ] || { echo "FAIL - guard missing at $GUARD"; exit 1; }
[ -n "$MISE_AUBX" ] || { echo "skip - no mise aube install to shadow the guard"; exit 0; }

fail=0
assert_resolves_guard() {
  local label="$1" got="$2"
  # Identity, not spelling: ~/.local/bin/aubx is a symlink to the guard, and a
  # path-string comparison called that correct resolution a failure. A genuinely
  # different file (the mise shim, a Homebrew build) is what -ef still catches.
  if [ -n "$got" ] && [ "$got" -ef "$GUARD" ]; then
    echo "ok   - $label resolves the guard"
  else
    echo "FAIL - $label resolved $got"
    fail=1
  fi
}

# A PATH shaped like a stale harness environment: mise's install bin first,
# ~/.agents/bin present but late.
stale="/usr/bin:/bin:$MISE_AUBX:$HOME/.agents/bin"

for shell in "bash -lc" "bash -ic" "sh -lc" "zsh -lc" "zsh -c"; do
  # shellcheck disable=SC2086
  assert_resolves_guard "$shell" "$(env -i HOME="$HOME" PATH="$stale" TERM=dumb $shell 'command -v aubx' 2>/dev/null)"
done

# A child of a fixed shell inherits the fixed order, so `bash -c` / `sh -c`
# (which read no rc files) stay confined too.
assert_resolves_guard "bash -lc -> bash -c" \
  "$(env -i HOME="$HOME" PATH="$stale" TERM=dumb bash -lc 'bash -c "command -v aubx"' 2>/dev/null)"
assert_resolves_guard "sh -lc -> sh -c" \
  "$(env -i HOME="$HOME" PATH="$stale" TERM=dumb sh -lc 'sh -c "command -v aubx"' 2>/dev/null)"

[ "$fail" -eq 0 ] && echo "all shell entry points resolve the aubx guard"
exit "$fail"
