#!/usr/bin/env bash
# Proves the roster install record stops claiming skills the roster does not
# have.
#
# Proof and install runs that source a skill from a throwaway directory leave a
# record entry behind when that source disappears: the entry names a path that
# no longer exists and no folder sits in available-skills. Nothing removed it,
# so `aubx skills update -g` re-resolved dead sources on every run and the
# roster record drifted from what is actually installed.
#
# Fails when: a normal confined run leaves a ghost entry in the record, drops a
# real entry, or writes outside available-skills.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd -P)"
WRAPPER="$BIN/aubx-skills"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

FHOME="$TMP/home"
mkdir -p "$FHOME/.agents/available-skills" "$TMP/bin"
export HOME="$FHOME" AGENTS_HOME="$FHOME/.agents"
AVAIL="$FHOME/.agents/available-skills"
RECORD="$AVAIL/.skill-lock.json"

# One real skill on disk, plus two record entries with no folder and a source
# path that no longer exists.
mkdir -p "$AVAIL/real-skill"
printf -- '---\nname: real-skill\n---\n' >"$AVAIL/real-skill/SKILL.md"
cat >"$RECORD" <<'JSON'
{"version":3,"skills":{"real-skill":{"source":"example/repo"},"ghost-a":{"source":"/tmp/gone-a/ghost-a"},"ghost-b":{"source":"/tmp/gone-b/ghost-b"}}}
JSON

# Stub installer: installs nothing, writes nothing. The prune must not depend on
# the installer having run.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$TMP/bin/aubx"

PATH="$TMP/bin:$PATH" "$WRAPPER" skills update -g >"$TMP/run.log" 2>&1
rc=$?
assert "confined run exits 0" "[ $rc -eq 0 ]"
assert "record still parses" "jq -e . '$RECORD' >/dev/null 2>&1"
assert "ghost entry ghost-a dropped" "! jq -e '.skills[\"ghost-a\"]' '$RECORD' >/dev/null 2>&1"
assert "ghost entry ghost-b dropped" "! jq -e '.skills[\"ghost-b\"]' '$RECORD' >/dev/null 2>&1"
assert "real entry kept" "jq -e '.skills[\"real-skill\"]' '$RECORD' >/dev/null 2>&1"
assert "real skill folder kept" "[ -f '$AVAIL/real-skill/SKILL.md' ]"
assert "run reported the prune" "grep -q 'dropped record entry' '$TMP/run.log'"
assert "no temp file left beside the record" "! ls -a '$AVAIL' | grep -q 'skill-lock.tmp'"
assert "no writes outside available-skills" "! grep -q 'WROTE OUTSIDE' '$TMP/run.log'"
[ "$fail" -eq 0 ] || { echo "--- run log:"; tail -20 "$TMP/run.log"; echo "--- record:"; cat "$RECORD"; }
exit "$fail"
