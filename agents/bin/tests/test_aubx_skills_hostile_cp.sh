#!/usr/bin/env bash
# Proves aubx-skills does not inherit whatever `cp` PATH resolves to.
#
# This machine shadows /bin/cp with a reflink wrapper whose directory semantics
# differ (it always nests into the destination, so `cp -R src dest` lands at
# dest/src) and which can abort with "Failed to preserve ownership" partway
# through a run. A confiner that calls the ambient `cp` fails with it: skills
# landed one level too deep and a real install aborted after a few folders.
#
# The wrapper must pin its own copier, stage the copy, and swap it in. Here the
# shim is a `cp` that always fails, which is the worst case of the same bug.
set -uo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/skills" "$TMP/bin"

# A `cp` that refuses every invocation, first on PATH.
cat >"$TMP/bin/cp" <<'SHIM'
#!/usr/bin/env bash
echo "Error copying file: Failed to copy: Failed to preserve 'ownership'" >&2
exit 1
SHIM
chmod +x "$TMP/bin/cp"

# Stand-in for `aubx skills add -g`: derives every path from $HOME, exactly like
# the real installer.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
name=""; prev=""
for a in "$@"; do [ "$prev" = "--skill" ] && name="$a"; prev="$a"; done
[ -n "$name" ] || { echo "stub: no --skill given" >&2; exit 1; }
mkdir -p "$AGENTS_HOME/skills/$name"
printf -- '---\nname: %s\ndescription: fixture\n---\n' "$name" >"$AGENTS_HOME/skills/$name/SKILL.md"
printf -- '{"version":3,"skills":{"%s":{"source":"example/repo"}}}\n' "$name" >"$AGENTS_HOME/.skill-lock.json"
STUB
chmod +x "$TMP/bin/aubx"

PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo-skill -y >"$TMP/run.log" 2>&1
rc=$?

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

assert "exited 0 despite a hostile cp"  "[ $rc -eq 0 ]"
assert "skill landed at the top level"  "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "no nested duplicate copy"       "[ ! -e \"$AGENTS_HOME/available-skills/demo-skill/demo-skill\" ]"
assert "no staging residue"             "[ -z \"\$(find \"$AGENTS_HOME/available-skills\" -maxdepth 1 -name '.*.incoming.*' -print)\" ]"
assert "no writes outside the roster"   "grep -q 'no writes outside' '$TMP/run.log' && [ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
exit "$fail"
