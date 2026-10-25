#!/usr/bin/env bash
# Proves the confiner never resolves the aubx guard as its "real" installer.
#
# On this machine the guard is installed twice: ~/.agents/bin/aubx and a symlink
# at ~/.local/bin/aubx -> ~/.agents/bin/aubx, and ~/.local/bin comes first on
# PATH. aubx-skills skipped only its own directory ($SELF_DIR) when scanning
# PATH, so it picked the ~/.local/bin symlink, ran the guard, and the guard
# refused with "confiner re-entered itself". Every global install died there.
#
# Same file, different directory: the skip has to compare file identity, not a
# directory name.
set -uo pipefail

REAL_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
WRAPPER="$REAL_DIR/aubx-skills"
GUARD="$REAL_DIR/aubx"
[ -x "$GUARD" ] || { echo "FAIL - guard missing at $GUARD"; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$TMP/installer" "$TMP/shim"

# The real installer stand-in: reaching it is what this test asserts.
cat >"$TMP/installer/aubx" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >"$TMP/argv.log"
STUB
chmod +x "$TMP/installer/aubx"

# The guard, reachable under a second name in a directory EARLIER on PATH —
# exactly the ~/.local/bin/aubx -> ~/.agents/bin/aubx arrangement.
ln -s "$GUARD" "$TMP/shim/aubx"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

PATH="$TMP/shim:$TMP/installer:$PATH" "$WRAPPER" add example/repo -g -y >"$TMP/run.log" 2>&1
rc=$?

assert "install exits 0"                "[ $rc -eq 0 ]"
assert "guard symlink was skipped"      "grep -q '$TMP/installer/aubx' '$TMP/run.log'"
assert "reached the real installer"     "[ -f '$TMP/argv.log' ]"
assert "installer got the package"      "grep -q 'example/repo' '$TMP/argv.log' 2>/dev/null"
assert "no confiner re-entry"           "! grep -q 'confiner re-entered itself' '$TMP/run.log'"

exit "$fail"
