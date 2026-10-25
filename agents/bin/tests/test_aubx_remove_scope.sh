#!/usr/bin/env bash
# Proves `aubx skills remove|rm` (and the `skills` shim's remove) is confined to
# available-skills, the same way installs are.
#
# A remove deletes three things an install writes: the roster folder, the
# harness links to it, and the install-record entry. Left unconfined it deleted
# harness links and rewrote ~/.agents/.skill-lock.json — both outside the roster.
#
# The stub stands in for the real installer: it deletes inside its throwaway
# HOME exactly like the CLI does, so what the wrapper mirrors into the real
# machine is what gets asserted here.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd -P)"
GUARD="$BIN/aubx"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

FAKE_HOME="$TMP/home"
REAL_DIR="$TMP/real"
GUARD_DIR="$TMP/guard"
mkdir -p "$REAL_DIR" "$GUARD_DIR"
cp "$GUARD" "$GUARD_DIR/aubx"
cp "$BIN/aubx-skills" "$GUARD_DIR/aubx-skills"
chmod +x "$GUARD_DIR/aubx" "$GUARD_DIR/aubx-skills"

cat >"$REAL_DIR/aubx" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$HOME" >>"$PROBE_LOG"
[ "${1:-}" = "skills" ] || exit 0
verb="${2:-}"; shift 2 || true
case "$verb" in
  remove|rm)
    names=(); all=0
    for a in "$@"; do
      case "$a" in
        --all) all=1 ;;
        -*) ;;
        *) names+=("$a") ;;
      esac
    done
    if [ "$all" -eq 1 ]; then
      names=()
      for d in "$AGENTS_HOME"/skills/*; do
        [ -d "$d" ] && names+=("$(basename "$d")")
      done
    fi
    [ "${#names[@]}" -gt 0 ] || { echo "stub: no skill names" >&2; exit 2; }
    rc=0
    for n in "${names[@]}"; do
      if [ ! -e "$AGENTS_HOME/skills/$n" ]; then
        echo "stub: not installed: $n" >&2; rc=1; continue
      fi
      rm -rf "$AGENTS_HOME/skills/$n"
      rm -f "$HOME/.claude/skills/$n" "$HOME/.codex/skills/$n"
      if command -v jq >/dev/null 2>&1 && [ -f "$AGENTS_HOME/.skill-lock.json" ]; then
        jq --arg n "$n" 'del(.skills[$n])' "$AGENTS_HOME/.skill-lock.json" \
          >"$AGENTS_HOME/.skill-lock.json.t" && mv "$AGENTS_HOME/.skill-lock.json.t" "$AGENTS_HOME/.skill-lock.json"
      fi
    done
    exit "$rc"
    ;;
esac
exit 0
STUB
chmod +x "$REAL_DIR/aubx"

# The machine as it is here: available-skills is the only roster, ~/.agents/skills
# reaches it through a symlink, one harness link points into the roster, and one
# points at a store this wrapper does not own.
setup_home() {
  rm -rf "$FAKE_HOME"
  mkdir -p "$FAKE_HOME/.agents/available-skills/alpha" \
           "$FAKE_HOME/.agents/available-skills/beta" \
           "$FAKE_HOME/.claude/skills" "$FAKE_HOME/.codex/skills" "$FAKE_HOME/elsewhere"
  printf -- '---\nname: alpha\ndescription: fixture\n---\n' >"$FAKE_HOME/.agents/available-skills/alpha/SKILL.md"
  printf -- '---\nname: beta\ndescription: fixture\n---\n' >"$FAKE_HOME/.agents/available-skills/beta/SKILL.md"
  printf '{"version":3,"skills":{"alpha":{"source":"example/repo"},"beta":{"source":"example/repo"}}}\n' \
    >"$FAKE_HOME/.agents/available-skills/.skill-lock.json"
  ln -sfn available-skills "$FAKE_HOME/.agents/skills"
  ln -sfn "$FAKE_HOME/.agents/available-skills/alpha" "$FAKE_HOME/.claude/skills/alpha"
  ln -sfn "$FAKE_HOME/elsewhere" "$FAKE_HOME/.codex/skills/foreign"
}

snap() {
  { find "$FAKE_HOME/.agents" -mindepth 1 -maxdepth 1 ! -name available-skills -print 2>/dev/null
    for r in "$FAKE_HOME"/.claude/skills "$FAKE_HOME"/.codex/skills; do
      [ -d "$r" ] && find "$r" -mindepth 1 -maxdepth 1 -print 2>/dev/null
    done
  } | sort
}

run_guard() { PATH="$REAL_DIR:$GUARD_DIR:$PATH" HOME="$FAKE_HOME" AGENTS_HOME="$FAKE_HOME/.agents" \
              PROBE_LOG="$TMP/home.log" "$GUARD_DIR/aubx" "$@"; }

# Case A: remove one skill. The roster folder and its record entry go, the link
# to it goes, another store's link stays, and nothing new appears outside.
setup_home
: >"$TMP/home.log"
snap >"$TMP/a.before"
run_guard skills remove alpha -g -y >"$TMP/a.log" 2>&1
rc=$?
snap >"$TMP/a.after"
assert "case A exit 0"                  "[ $rc -eq 0 ]"
assert "case A removed the roster copy" "[ ! -e '$FAKE_HOME/.agents/available-skills/alpha' ]"
assert "case A kept the other skill"    "[ -f '$FAKE_HOME/.agents/available-skills/beta/SKILL.md' ]"
assert "case A pruned the record"       "! jq -e '.skills.alpha' '$FAKE_HOME/.agents/available-skills/.skill-lock.json' >/dev/null"
assert "case A kept the record entry for beta" "jq -e '.skills.beta' '$FAKE_HOME/.agents/available-skills/.skill-lock.json' >/dev/null"
assert "case A dropped the roster link" "[ ! -L '$FAKE_HOME/.claude/skills/alpha' ]"
assert "case A left another store's link" "[ -L '$FAKE_HOME/.codex/skills/foreign' ]"
assert "case A installer ran under a scratch HOME" "! grep -qx '$FAKE_HOME' '$TMP/home.log'"
assert "case A says no writes outside"  "grep -q 'no writes outside' '$TMP/a.log'"
assert "case A wrote no new entry outside" "[ -z \"\$(comm -13 '$TMP/a.before' '$TMP/a.after')\" ]"

# Case B: the rm alias takes the same path.
setup_home
snap >"$TMP/b.before"
run_guard skills rm beta -g -y >"$TMP/b.log" 2>&1
rc=$?
snap >"$TMP/b.after"
assert "case B rm exit 0"              "[ $rc -eq 0 ]"
assert "case B removed beta"           "[ ! -e '$FAKE_HOME/.agents/available-skills/beta' ]"
assert "case B wrote no new entry outside" "[ -z \"\$(comm -13 '$TMP/b.before' '$TMP/b.after')\" ]"

# Case C: a name that is not installed fails without deleting anything.
setup_home
snap >"$TMP/c.before"
run_guard skills remove nosuch -g -y >"$TMP/c.log" 2>&1
rc=$?
snap >"$TMP/c.after"
assert "case C exits nonzero"          "[ $rc -ne 0 ]"
assert "case C removed nothing"        "[ -f '$FAKE_HOME/.agents/available-skills/alpha/SKILL.md' ] && [ -f '$FAKE_HOME/.agents/available-skills/beta/SKILL.md' ]"
assert "case C never claims clean"     "! grep -q 'no writes outside' '$TMP/c.log'"
assert "case C wrote nothing outside"  "[ -z \"\$(comm -3 '$TMP/c.before' '$TMP/c.after')\" ]"

# Case D: --all clears the roster and leaves no skill record behind.
setup_home
run_guard skills remove --all -g -y >"$TMP/d.log" 2>&1
rc=$?
assert "case D --all exit 0"           "[ $rc -eq 0 ]"
assert "case D roster emptied"         "[ -z \"\$(find '$FAKE_HOME/.agents/available-skills' -mindepth 1 -maxdepth 1 -type d)\" ]"
assert "case D record emptied"         "[ \"\$(jq -r '.skills|length' '$FAKE_HOME/.agents/available-skills/.skill-lock.json')\" = 0 ]"
assert "case D no stray install record at ~/.agents" "[ ! -e '$FAKE_HOME/.agents/.skill-lock.json' ]"

if [ "$fail" -ne 0 ]; then
  echo "FAILED: remove is not confined to available-skills"
  exit 1
fi
echo "aubx skills remove writes only to available-skills"
