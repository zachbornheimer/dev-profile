#!/usr/bin/env bash
# Proves `skills remove` obeys the same scope contract as `skills add`: the
# removal is routed through aubx-skills and its only durable writes are inside
# $AGENTS_HOME/available-skills. Runs the real confiner against a stub installer
# so the check is offline and deterministic.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd -P)"
GUARD="$BIN/aubx"
AUBE_GUARD="$BIN/aube"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

FAKE_HOME="$TMP/home"

# --- routing: both entry points must hand `remove` to the confiner -----------
mkdir -p "$TMP/route/guard" "$TMP/route/real" "$TMP/route/home/.agents"
cp "$GUARD" "$TMP/route/guard/aubx"
cp "$AUBE_GUARD" "$TMP/route/guard/aube"
cat >"$TMP/route/guard/aubx-skills" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$HOME/confined.log"
STUB
cat >"$TMP/route/real/aubx" <<'STUB'
#!/usr/bin/env bash
printf 'aubx %s\n' "$*" >>"$HOME/argv.log"
STUB
cat >"$TMP/route/real/aube" <<'STUB'
#!/usr/bin/env bash
printf 'aube %s\n' "$*" >>"$HOME/argv.log"
STUB
chmod +x "$TMP/route/guard/"* "$TMP/route/real/"*

HOME="$TMP/route/home" AGENTS_HOME="$TMP/route/home/.agents" \
  PATH="$TMP/route/guard:$TMP/route/real:$PATH" "$TMP/route/guard/aubx" skills remove webapp-demo -g -y >"$TMP/route/a.log" 2>&1
HOME="$TMP/route/home" AGENTS_HOME="$TMP/route/home/.agents" \
  PATH="$TMP/route/guard:$TMP/route/real:$PATH" "$TMP/route/guard/aube" skills remove webapp-demo -g -y >"$TMP/route/b.log" 2>&1
assert "aubx skills remove routed to aubx-skills" "grep -q 'remove webapp-demo -g -y' '$TMP/route/home/confined.log'"
assert "aubx skills remove never hit the real CLI" "[ ! -f '$TMP/route/home/argv.log' ] || ! grep -q 'skills remove' '$TMP/route/home/argv.log'"

# --- scope: removal writes only inside available-skills ---------------------
# Mirrors the machine: available-skills is the one real tree, .agents/skills is
# the symlink harness entries reach it through, and one harness root holds a
# link to the skill about to be removed.
setup_home() {
  rm -rf "$FAKE_HOME"
  mkdir -p "$FAKE_HOME/.agents/available-skills/webapp-demo" "$FAKE_HOME/.claude/skills" "$FAKE_HOME/.codex/skills"
  ln -sfn available-skills "$FAKE_HOME/.agents/skills"
  printf -- '---\nname: webapp-demo\ndescription: fixture\n---\n' >"$FAKE_HOME/.agents/available-skills/webapp-demo/SKILL.md"
  printf '{"version":3,"skills":{"webapp-demo":{"source":"example/repo"}}}\n' >"$FAKE_HOME/.agents/available-skills/.skill-lock.json"
  ln -sfn "../../.agents/skills/webapp-demo" "$FAKE_HOME/.claude/skills/webapp-demo"
  export HOME="$FAKE_HOME" AGENTS_HOME="$FAKE_HOME/.agents"
}

snap() {
  {
    find "$FAKE_HOME/.agents" -mindepth 1 -maxdepth 1 ! -name available-skills -print 2>/dev/null
    for r in "$FAKE_HOME"/.claude/skills "$FAKE_HOME"/.codex/skills "$FAKE_HOME"/.cursor/skills \
             "$FAKE_HOME"/.grok/skills "$FAKE_HOME"/.gemini/skills "$FAKE_HOME"/.config/opencode/skills; do
      [ -d "$r" ] && find "$r" -mindepth 1 -maxdepth 1 -print 2>/dev/null
    done
    find "$FAKE_HOME" -mindepth 1 -maxdepth 1 -print 2>/dev/null
  } | sort
}

# $1 = extra shell the stub runs after performing the removal in its scratch tree.
make_stub() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
[ "\$1" = skills ] && [ "\$2" = remove ] || { echo "stub: unexpected: \$*" >&2; exit 1; }
for a in "\$@"; do
  case "\$a" in -*) continue ;; esac
  case "\$a" in skills|remove) continue ;; esac
  rm -rf "\$AGENTS_HOME/skills/\$a"
done
$1
STUB
  chmod +x "$TMP/bin/aubx"
}

# Case A: clean removal. Folder gone from scope, dangling harness link dropped,
# record pruned, nothing else touched.
setup_home
make_stub ':'
snap >"$TMP/a.before"
PATH="$TMP/bin:$PATH" "$BIN/aubx-skills" skills remove webapp-demo -g -y >"$TMP/a.log" 2>&1
rc=$?
snap >"$TMP/a.after"
assert "case A exit 0"                    "[ $rc -eq 0 ]"
assert "case A removed the skill"         "[ ! -e '$FAKE_HOME/.agents/available-skills/webapp-demo' ]"
assert "case A dropped the harness link"  "[ ! -L '$FAKE_HOME/.claude/skills/webapp-demo' ]"
assert "case A pruned the record"         "! grep -q webapp-demo '$FAKE_HOME/.agents/available-skills/.skill-lock.json'"
assert "case A no writes outside"         "[ -z \"\$(comm -13 '$TMP/a.before' '$TMP/a.after')\" ]"
assert "case A says so"                   "grep -q 'no writes outside' '$TMP/a.log'"
assert "case A left no record outside"    "[ ! -e '$FAKE_HOME/.agents/.skill-lock.json' ]"

# Case B: installer deletes something outside scope. Name it and exit 3.
setup_home
mkdir -p "$FAKE_HOME/.codex/skills/rogue-real"
printf 'x\n' >"$FAKE_HOME/.codex/skills/rogue-real/SKILL.md"
make_stub 'rm -rf "'"$FAKE_HOME"'/.codex/skills/rogue-real"'
PATH="$TMP/bin:$PATH" "$BIN/aubx-skills" skills remove webapp-demo -g -y >"$TMP/b.log" 2>&1
rc=$?
assert "case B exit 3"                 "[ $rc -eq 3 ]"
assert "case B names the violation"    "grep -q 'WROTE OUTSIDE' '$TMP/b.log' && grep -q rogue-real '$TMP/b.log'"
assert "case B never claims clean"     "! grep -q 'no writes outside' '$TMP/b.log'"

# Case C: dry run reports and changes nothing.
setup_home
make_stub ':'
snap >"$TMP/c.before"
PATH="$TMP/bin:$PATH" DRY_RUN=1 "$BIN/aubx-skills" skills remove webapp-demo -g -y >"$TMP/c.log" 2>&1
rc=$?
snap >"$TMP/c.after"
assert "case C exit 0"                "[ $rc -eq 0 ]"
assert "case C kept the skill"        "[ -e '$FAKE_HOME/.agents/available-skills/webapp-demo/SKILL.md' ]"
assert "case C no changes"            "[ -z \"\$(comm -3 '$TMP/c.before' '$TMP/c.after')\" ]"
assert "case C said what it would do" "grep -q 'would remove' '$TMP/c.log'"

if [ "$fail" -ne 0 ]; then
  echo "FAILED: skills remove is not confined to available-skills"
  exit 1
fi
echo "skills remove writes only to available-skills"
