#!/usr/bin/env bash
# Proves aubx-skills rejects an argv its installer cannot parse, instead of
# forwarding it into the cryptic "Missing required argument: source".
# The skills CLI's -s/-a/--subagent parsers swallow every following non-flag
# word, so `add -s '*' example/repo` reads the package as a skill name.
set -uo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$TMP/bin"

# Records the argv it was handed; the wrapper must never reach it on a bad parse.
cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >"$TMP/argv.log"
STUB
chmod +x "$TMP/bin/aubx"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

# Swallowed source: the exact argv that failed against the real installer.
PATH="$TMP/bin:$PATH" "$WRAPPER" add -g -y -s '*' example/repo >"$TMP/bad.log" 2>&1
rc=$?
assert "swallowed source exits 2"        "[ $rc -eq 2 ]"
assert "names the cause"                 "grep -q 'no package source' '$TMP/bad.log'"
assert "names the fix"                   "grep -q 'put the package first' '$TMP/bad.log'"
assert "never reached the installer"     "[ ! -e '$TMP/argv.log' ]"

# Same flags, source first: it must pass through untouched.
PATH="$TMP/bin:$PATH" "$WRAPPER" add example/repo -g -y -s '*' >"$TMP/good.log" 2>&1
rc=$?
assert "source-first exits 0"            "[ $rc -eq 0 ]"
assert "source-first reached installer"  "grep -q 'example/repo' '$TMP/argv.log'"

exit "$fail"
