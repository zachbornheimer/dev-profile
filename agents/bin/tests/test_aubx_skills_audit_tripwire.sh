#!/usr/bin/env bash
# test_aubx_skills_audit_tripwire — prove the write-scope audit actually looks.
#
# The audit used to be vacuous for the $AGENTS_HOME tree. A `#` comment sat
# inside the backslash-continued `find` in audit_snapshot(). Bash ends the
# logical line at that comment, so the rest of the expression became a second
# command that does not exist (`-o` is not a program): `-o -print` and the
# `>>"$out"` redirect never ran. Consequences, both reproduced in arm C below:
#   * nothing under $AGENTS_HOME was ever listed, so a real file planted there
#     during a run was invisible and the run printed "no writes outside ..."
#     and exited 0;
#   * the implicit `-print` that POSIX find appends printed every prune-listed
#     entry (available-skills, *.log, .DS_Store, ...) to stdout — a path dump.
# The harness skill roots were still audited, because their `find` is a separate
# command. So the discriminating plant is inside $AGENTS_HOME, not a harness
# root: a harness-root leak was caught even before the fix.
#
# Arms:
#   A  clean confined global install lands only in <home>/.agents/available-skills,
#      prints no absolute-path dump on stdout, and claims the clean scope.
#                                                        (red pre-fix: dump)
#   B  the installer writes a real directory straight into $AGENTS_HOME during
#      the run -> exit 3 and the path is named.          (red pre-fix: exit 0)
#   B2 the installer writes a real directory into a harness skill root -> exit 3.
#   C  audit_snapshot lists the $AGENTS_HOME tree and writes it to its output
#      file instead of stdout.                           (red pre-fix: both)
#
# Discriminating arm: B. Against the pre-fix script it exits 0 with the leaked
# directory on disk, so this test fails there and passes after the fix.
#
# Deterministic and offline: a stub installer stands in for aube, so the test
# proves the wrapper's audit, not the network.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd -P)"
WRAPPER="$BIN/aubx-skills"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/aubx-audit-tripwire.XXXXXX")" || exit 1
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

setup_home() {
  rm -rf "${TMP:?}/home"
  mkdir -p "$TMP/home/.agents" "$TMP/home/.claude/skills" "$TMP/home/.codex/skills"
  export HOME="$TMP/home" AGENTS_HOME="$TMP/home/.agents"
}

# $1 = shell the stub runs after installing the skill into the scratch HOME the
# wrapper hands it. Inside the stub, $HOME is the throwaway scratch tree; the
# real test home is baked in as an absolute path at heredoc time.
make_stub() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
name=""; prev=""
for a in "\$@"; do [ "\$prev" = "--skill" ] && name="\$a"; prev="\$a"; done
[ -n "\$name" ] || { echo "stub: no --skill given: \$*" >&2; exit 2; }
mkdir -p "\$AGENTS_HOME/skills/\$name"
printf -- '---\nname: %s\ndescription: probe skill for the audit tripwire\n---\n' \
  "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
$1
STUB
  chmod +x "$TMP/bin/aubx"
}

# Case A: clean confined install.
setup_home
make_stub ':'
PATH="$TMP/bin:$PATH" timeout 240 "$WRAPPER" skills add example/repo --skill probe-skill -g -y \
  >"$TMP/a.log" 2>&1
rc=$?
# A find dump lands at column 0; the wrapper's own notes are prefixed, so an
# anchored match counts dump lines only.
dumped="$(grep -c "^$HOME/" "$TMP/a.log" 2>/dev/null || true)"
assert "case A exit 0"                       "[ $rc -eq 0 ]"
assert "case A landed in available-skills"   "[ -f \"$HOME/.agents/available-skills/probe-skill/SKILL.md\" ]"
assert "case A claims the clean scope"       "grep -q 'no writes outside' '$TMP/a.log'"
assert "case A dumps no path to stdout"      "[ \"${dumped:-0}\" -eq 0 ]"

# Case B: installer reaches the real $AGENTS_HOME during the run. The audit must
# see the new entry, name it, and exit 3.
setup_home
make_stub "mkdir -p '$HOME/.agents/leaked-probe'; printf x >'$HOME/.agents/leaked-probe/SKILL.md'"
PATH="$TMP/bin:$PATH" timeout 240 "$WRAPPER" skills add example/repo --skill probe-skill -g -y \
  >"$TMP/b.log" 2>&1
rc=$?
assert "case B exit 3 (leak under AGENTS_HOME detected)" "[ $rc -eq 3 ]"
assert "case B names the violation"          "grep -q 'WROTE OUTSIDE' '$TMP/b.log' && grep -q leaked-probe '$TMP/b.log'"
assert "case B never claims clean"           "! grep -q 'no writes outside' '$TMP/b.log'"

# Case B2: same via a harness skill root. This arm was already live before the
# fix; it is kept so the other half of the tripwire cannot regress.
setup_home
make_stub "mkdir -p '$HOME/.codex/skills/leaked-probe'; printf x >'$HOME/.codex/skills/leaked-probe/SKILL.md'"
PATH="$TMP/bin:$PATH" timeout 240 "$WRAPPER" skills add example/repo --skill probe-skill -g -y \
  >"$TMP/b2.log" 2>&1
rc=$?
assert "case B2 exit 3 (harness-root leak detected)" "[ $rc -eq 3 ]"
assert "case B2 names the violation"         "grep -q 'WROTE OUTSIDE' '$TMP/b2.log' && grep -q leaked-probe '$TMP/b2.log'"

# Case C: the audit function itself, extracted from the shipped script (never
# copied), driven against a tree with known entries. This is the direct
# anti-regression for the empty-file bug: an entry under AGENTS_HOME must reach
# the snapshot file, and nothing may reach stdout.
awk '/^audit_snapshot\(\) \{/{f=1} f{print} f && /^\}$/{exit}' "$WRAPPER" >"$TMP/audit-fn.sh"
assert "case C extracted the audit function" "grep -q 'audit_snapshot() {' '$TMP/audit-fn.sh' && grep -q -- '-o -print' '$TMP/audit-fn.sh'"
setup_home
mkdir -p "$HOME/.agents/planted-under-agents" "$HOME/.agents/available-skills/already-installed" \
         "$HOME/.claude/skills/audit-probe"
printf x >"$HOME/.agents/planted-under-agents/SKILL.md"
printf -- '---\nname: already-installed\n---\n' >"$HOME/.agents/available-skills/already-installed/SKILL.md"
printf -- '---\nname: audit-probe\n---\n' >"$HOME/.claude/skills/audit-probe/SKILL.md"
probe_out="$TMP/audit-snapshot.txt"
(
  set -uo pipefail
  AGENTS_HOME="$HOME/.agents"
  # shellcheck disable=SC2034 # read by the sourced audit-fn.sh
  REAL_HOME="$HOME"
  # shellcheck disable=SC2034 # read by the sourced audit-fn.sh
  LINK_ROOTS=("$HOME/.claude/skills" "$HOME/.codex/skills")
  . "$TMP/audit-fn.sh"
  audit_snapshot "$probe_out"
) >"$TMP/c.stdout" 2>/dev/null
assert "case C lists the AGENTS_HOME tree"    "grep -q 'agents/planted-under-agents' '$probe_out'"
assert "case C lists the harness root"        "grep -q 'claude/skills/audit-probe' '$probe_out'"
assert "case C prunes available-skills"       "! grep -q 'available-skills/already-installed' '$probe_out'"
assert "case C wrote the file, not stdout"    "[ -s '$probe_out' ] && [ ! -s '$TMP/c.stdout' ]"

[ "$fail" -eq 0 ] && echo "PASS $(basename "$0")"
exit "$fail"
