#!/usr/bin/env bash
# Proves aubx-skills never deletes another process's work. The audit compares
# before/after snapshots of shared harness roots, so any *other* process that
# writes a link into ~/.claude/skills during the install window shows up as new
# and used to be removed as if this run had leaked it. Deletion is a write
# outside available-skills, and the user's link is not ours to drop.
#
# The run may only clean up a link for a skill IT installed.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$BIN/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

REAL_HOME="$TMP/home"
mkdir -p "$REAL_HOME/.agents/available-skills/demo" "$REAL_HOME/.claude/skills" "$TMP/bin"
printf -- '---\nname: demo\n---\n' >"$REAL_HOME/.agents/available-skills/demo/SKILL.md"
mkdir -p "$REAL_HOME/.agents/available-skills/other-tool"
printf -- '---\nname: other-tool\n---\n' >"$REAL_HOME/.agents/available-skills/other-tool/SKILL.md"
ln -sfn available-skills "$REAL_HOME/.agents/skills"

# The installer installs `demo` under scratch HOME and also links a skill that
# belongs to some other process (`other-tool`), modelling a concurrent writer
# touching the real ~/.claude/skills during this run's window.
cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
name=""; prev=""
for a in "\$@"; do [ "\$prev" = "--skill" ] && name="\$a"; prev="\$a"; done
mkdir -p "\$AGENTS_HOME/skills/\$name"
printf -- '---\nname: %s\n---\n' "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
mkdir -p "$REAL_HOME/.claude/skills"
ln -sfn "$REAL_HOME/.agents/skills/other-tool" "$REAL_HOME/.claude/skills/other-tool"
STUB
chmod +x "$TMP/bin/aubx"

HOME="$REAL_HOME" AGENTS_HOME="$REAL_HOME/.agents" PATH="$TMP/bin:$PATH" \
  "$WRAPPER" skills add example/repo --skill demo -g -y >"$TMP/out.log" 2>&1
rc=$?

assert "exit 0"                          "[ $rc -eq 0 ]"
assert "installed skill landed"          "[ -f \"$REAL_HOME/.agents/available-skills/demo/SKILL.md\" ]"
assert "another process's link survives" "[ -L \"$REAL_HOME/.claude/skills/other-tool\" ]"
assert "surviving link still resolves"   "[ -e \"$REAL_HOME/.claude/skills/other-tool\" ]"
assert "no violation reported"           "! grep -q 'WROTE OUTSIDE' '$TMP/out.log'"

exit "$fail"
