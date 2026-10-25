#!/usr/bin/env bash
# Proves aubx-skills works when it is entered through a symlink, which is how it
# is installed (~/.local/bin/aubx-skills -> ~/.agents/bin/aubx-skills).
#
# The wrapper has to skip its own directory when it looks for the real aube
# installer: resolving to the ~/.agents/bin/aubx guard made the guard re-enter
# the confiner, so every global install died with
# "aubx: confiner re-entered itself; refusing to nest a second scratch HOME".
# A dirname-only SELF_DIR points at the symlink's directory, so the skip missed.
set -uo pipefail

REAL_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
WRAPPER="$REAL_DIR/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$TMP/bin"

# The installer stand-in. It must be reached: reaching the guard instead is the
# failure this test exists for.
cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >"$TMP/argv.log"
STUB
chmod +x "$TMP/bin/aubx"

# Enter through a symlink, exactly like ~/.local/bin/aubx-skills.
ln -s "$WRAPPER" "$TMP/bin/aubx-skills"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

PATH="$TMP/bin:$PATH" "$TMP/bin/aubx-skills" add example/repo -g -y >"$TMP/run.log" 2>&1
rc=$?

assert "symlinked entry exits 0"          "[ $rc -eq 0 ]"
assert "reached the real installer"       "[ -f '$TMP/argv.log' ]"
assert "installer got the package"        "grep -q 'example/repo' '$TMP/argv.log' 2>/dev/null"
assert "no confiner re-entry"             "! grep -q 'confiner re-entered itself' '$TMP/run.log'"

exit "$fail"
