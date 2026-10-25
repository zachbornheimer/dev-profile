#!/usr/bin/env bash
# A failed install must leave nothing outside available-skills. The installer
# writes ~/.agents/.skill-lock.json before it knows whether the clone or the
# copy will succeed, so a run that installs nothing still trips that write. The
# wrapper has to remove it and must not import entries for skills that never
# landed, or the roster record starts claiming installs that do not exist.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$BIN/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

FAKE_HOME="$TMP/home"

setup_home() {
  rm -rf "$FAKE_HOME"
  mkdir -p "$FAKE_HOME/.agents/available-skills" "$FAKE_HOME/.claude/skills"
  export HOME="$FAKE_HOME" AGENTS_HOME="$FAKE_HOME/.agents"
}

# $1 = record body the installer writes to the real ~/.agents path
# $2 = exit status the installer returns
make_stub() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
printf '%s' '$1' >"\$REAL_HOME/.agents/.skill-lock.json"
echo "stub: install failed" >&2
exit $2
STUB
  chmod +x "$TMP/bin/aubx"
}

# Case A: nothing installed, record names a skill that never landed. The file
# must be gone and the ghost entry must not reach the roster record.
setup_home
make_stub '{"version":3,"skills":{"ghost":{"source":"example/repo"}}}' 1
PATH="$TMP/bin:$PATH" REAL_HOME="$FAKE_HOME" "$WRAPPER" skills add example/repo -g -y >"$TMP/a.log" 2>&1
rc=$?
assert "case A exits with the installer status" "[ $rc -eq 1 ]"
assert "case A left no record outside" \
  "[ ! -e '$FAKE_HOME/.agents/.skill-lock.json' ]"
assert "case A did not report a violation" "! grep -q 'WROTE OUTSIDE' '$TMP/a.log'"
assert "case A did not invent a roster entry" \
  "! jq -e '.skills.ghost' '$FAKE_HOME/.agents/available-skills/.skill-lock.json' >/dev/null 2>&1"

# Case B: the leaked record also lists a skill that really is installed. That
# entry is real state, so it is folded into the roster record instead of being
# thrown away with the file.
setup_home
mkdir -p "$FAKE_HOME/.agents/available-skills/real-one"
printf -- '---\nname: real-one\ndescription: fixture\n---\n' >"$FAKE_HOME/.agents/available-skills/real-one/SKILL.md"
make_stub '{"version":3,"skills":{"real-one":{"source":"example/repo"},"ghost":{"source":"example/repo"}}}' 1
PATH="$TMP/bin:$PATH" REAL_HOME="$FAKE_HOME" "$WRAPPER" skills add example/repo -g -y >"$TMP/b.log" 2>&1
rc=$?
assert "case B exits with the installer status" "[ $rc -eq 1 ]"
assert "case B left no record outside" "[ ! -e '$FAKE_HOME/.agents/.skill-lock.json' ]"
assert "case B kept the real entry" \
  "jq -e '.skills.\"real-one\"' '$FAKE_HOME/.agents/available-skills/.skill-lock.json' >/dev/null 2>&1"
assert "case B dropped the ghost entry" \
  "! jq -e '.skills.ghost' '$FAKE_HOME/.agents/available-skills/.skill-lock.json' >/dev/null 2>&1"
assert "case B did not report a violation" "! grep -q 'WROTE OUTSIDE' '$TMP/b.log'"
assert "case B still failed loudly" "grep -q 'installer exited 1' '$TMP/b.log'"

[ "$fail" -eq 0 ] && echo "PASS $(basename "$0")"
exit "$fail"
