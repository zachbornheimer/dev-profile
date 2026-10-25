#!/usr/bin/env bash
# Proves the audit separates the installer's writes from another process's.
#
# ~/.agents is a shared tree: hooks, tooling and other agents write inside it
# while an install runs. A full-depth snapshot called any new path there a leak,
# so an unrelated file (a test added under ~/.agents/bin/tests) failed a
# correctly confined install with exit 3. ~/.agents/bin is chezmoi-managed tool
# code that no skill installer derives a path into, so it is out of the audit's
# subject. The tripwire must still fire for the paths an installer can reach.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$BIN/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }
REAL_HOME="$TMP/home"

# $1 = shell snippet the installer runs after its normal scratch install; it
# models a second process (or a rogue installer) writing a real machine path.
make_stub() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
name=""
for a in "\$@"; do [ "\$prev" = "--skill" ] && name="\$a"; prev="\$a"; done
mkdir -p "\$AGENTS_HOME/skills/\$name"
printf -- '---\nname: %s\n---\n' "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
$1
STUB
  chmod +x "$TMP/bin/aubx"
}

setup_home() {
  rm -rf "${TMP:?}/home"
  mkdir -p "$REAL_HOME/.agents/available-skills" "$REAL_HOME/.agents/bin/tests" \
            "$REAL_HOME/.agents/hooks" "$REAL_HOME/.claude/skills"
  export HOME="$REAL_HOME" AGENTS_HOME="$REAL_HOME/.agents"
}

# Case A: another process adds a file deep under ~/.agents/bin during the run.
# Not the installer's write, not a leak, install still succeeds.
setup_home
make_stub "printf '#!/usr/bin/env bash\n' >'$REAL_HOME/.agents/bin/tests/added-during-run.sh'"
PATH="$TMP/bin:$PATH" "$WRAPPER" skills add example/repo --skill demo -g -y >"$TMP/a.log" 2>&1
rc=$?
assert "case A exit 0"                "[ $rc -eq 0 ]"
assert "case A reports no violation"  "! grep -q 'WROTE OUTSIDE' '$TMP/a.log'"
assert "case A installed the skill"   "[ -f '$REAL_HOME/.agents/available-skills/demo/SKILL.md' ]"

# Case B: a write into ~/.agents/hooks is still an escape: the tripwire did not
# get weaker, only narrower.
setup_home
make_stub "printf 'x\n' >'$REAL_HOME/.agents/hooks/planted.sh'"
PATH="$TMP/bin:$PATH" "$WRAPPER" skills add example/repo --skill demo -g -y >"$TMP/b.log" 2>&1
rc=$?
assert "case B exit 3"               "[ $rc -eq 3 ]"
assert "case B names the violation"  "grep -q 'planted.sh' '$TMP/b.log'"

# Case C: a new top-level entry under AGENTS_HOME is still an escape.
setup_home
make_stub "mkdir -p '$REAL_HOME/.agents/cache-from-installer'"
PATH="$TMP/bin:$PATH" "$WRAPPER" skills add example/repo --skill demo -g -y >"$TMP/c.log" 2>&1
rc=$?
assert "case C exit 3"               "[ $rc -eq 3 ]"
assert "case C names the violation"  "grep -q 'cache-from-installer' '$TMP/c.log'"

exit "$fail"
