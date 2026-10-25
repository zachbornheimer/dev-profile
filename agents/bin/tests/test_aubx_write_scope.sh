#!/usr/bin/env bash
# Proves the machine-wide scope contract for global aubx skill installs:
# after `aubx skills add|update`, the only durable write on the machine is
# inside $AGENTS_HOME/available-skills.
#
# Two halves:
#   1. Controlled runs through the guard with a stub installer (offline and
#      deterministic): a clean install, an installer that links a harness root,
#      an installer that writes a real directory outside, and an update.
#   2. A read-only audit of the real machine: no harness skill root may hold a
#      real copy of a skill that lives in available-skills, and $AGENTS_HOME may
#      not grow an install record or a real skills tree.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd -P)"
GUARD="$BIN/aubx"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
REAL_HOME="${REAL_HOME:-$HOME}"   # the machine, captured before any fixture rewrites HOME
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

FAKE_HOME="$TMP/home"

# Entries a run could create anywhere outside available-skills.
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

# Mirrors the machine: available-skills is the one real tree and .agents/skills
# is the symlink every harness entry point reaches it through.
setup_home() {
  rm -rf "$FAKE_HOME"
  mkdir -p "$FAKE_HOME/.agents/available-skills/seeded" "$FAKE_HOME/.claude/skills" "$FAKE_HOME/.codex/skills"
  ln -sfn available-skills "$FAKE_HOME/.agents/skills"
  printf -- '---\nname: seeded\ndescription: fixture\n---\n' >"$FAKE_HOME/.agents/available-skills/seeded/SKILL.md"
  export HOME="$FAKE_HOME" AGENTS_HOME="$FAKE_HOME/.agents"
}

# $1 = shell the stub installer runs after installing into its scratch AGENTS_HOME.
make_stub() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
name=""; prev=""
for a in "\$@"; do [ "\$prev" = "--skill" ] && name="\$a"; prev="\$a"; done
if [ -z "\$name" ]; then
  # update/remove pass the skill name positionally: skills update <name> -g -y
  for a in "\$@"; do
    case "\$a" in -*) continue ;; esac
    case "\$a" in skills|update|upgrade|remove|rm|add) continue ;; esac
    name="\$a"
  done
fi
[ -n "\$name" ] || { echo "stub: no --skill given: \$*" >&2; exit 1; }
mkdir -p "\$AGENTS_HOME/skills/\$name"
printf -- '---\nname: %s\ndescription: fixture\n---\n' "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
printf '{"version":3,"skills":{"%s":{"source":"example/repo"}}}\n' "\$name" >"\$AGENTS_HOME/.skill-lock.json"
$1
STUB
  chmod +x "$TMP/bin/aubx"
}

# Case A: clean install through the guard. One durable write, in scope only.
setup_home
make_stub ':'
snap >"$TMP/a.before"
PATH="$TMP/bin:$PATH" "$GUARD" skills add example/repo --skill webapp-demo -g -y >"$TMP/a.log" 2>&1
rc=$?
snap >"$TMP/a.after"
assert "case A exit 0"                 "[ $rc -eq 0 ]"
assert "case A installed into scope"   "[ -f '$FAKE_HOME/.agents/available-skills/webapp-demo/SKILL.md' ]"
assert "case A no writes outside"      "[ -z \"\$(comm -13 '$TMP/a.before' '$TMP/a.after')\" ]"
assert "case A says so"                "grep -q 'no writes outside' '$TMP/a.log'"
assert "case A left no install record outside" "[ ! -e '$FAKE_HOME/.agents/.skill-lock.json' ]"
assert "case A record lives in scope"  "grep -q webapp-demo '$FAKE_HOME/.agents/available-skills/.skill-lock.json'"

# Case B: installer links a real harness root (~/.claude/skills) to its scratch
# copy through ~/.agents/skills. The link reaches available-skills but is still
# a write outside scope, so it must be removed and the run must still succeed.
setup_home
make_stub 'mkdir -p "'"$FAKE_HOME"'/.claude/skills"; ln -sfn "../../.agents/skills/webapp-demo" "'"$FAKE_HOME"'/.claude/skills/webapp-demo"'
snap >"$TMP/b.before"
PATH="$TMP/bin:$PATH" "$GUARD" skills add example/repo --skill webapp-demo -g -y >"$TMP/b.log" 2>&1
rc=$?
snap >"$TMP/b.after"
assert "case B exit 0"                 "[ $rc -eq 0 ]"
assert "case B removed the harness link" "[ ! -L '$FAKE_HOME/.claude/skills/webapp-demo' ]"
assert "case B no writes outside"      "[ -z \"\$(comm -13 '$TMP/b.before' '$TMP/b.after')\" ]"

# Case C: installer writes a real directory outside scope. Report it, name it,
# exit 3, and never claim the run was clean.
setup_home
make_stub 'mkdir -p "'"$FAKE_HOME"'/.codex/skills/rogue"; echo x >"'"$FAKE_HOME"'/.codex/skills/rogue/SKILL.md"'
PATH="$TMP/bin:$PATH" "$GUARD" skills add example/repo --skill webapp-demo -g -y >"$TMP/c.log" 2>&1
rc=$?
assert "case C exit 3"                 "[ $rc -eq 3 ]"
assert "case C names the violation"    "grep -q 'WROTE OUTSIDE' '$TMP/c.log' && grep -q rogue '$TMP/c.log'"
assert "case C never claims clean"     "! grep -q 'no writes outside' '$TMP/c.log'"

# Case D: update path. Rewrites in scope, writes nothing else.
setup_home
make_stub ':'
PATH="$TMP/bin:$PATH" "$GUARD" skills add example/repo --skill webapp-demo -g -y >/dev/null 2>&1
printf '{"version":3,"skills":{"webapp-demo":{"source":"example/repo"}}}\n' >"$FAKE_HOME/.agents/available-skills/.skill-lock.json"
snap >"$TMP/d.before"
PATH="$TMP/bin:$PATH" "$GUARD" skills update webapp-demo -g -y >"$TMP/d.log" 2>&1
rc=$?
snap >"$TMP/d.after"
assert "case D exit 0"                 "[ $rc -eq 0 ]"
assert "case D no writes outside"      "[ -z \"\$(comm -13 '$TMP/d.before' '$TMP/d.after')\" ]"

# Case F: an install record left at AGENTS_HOME/.skill-lock.json is folded into
# the roster record and removed, so skill state never stays outside scope. An
# entry with no skill folder behind it is dropped, not carried over.
setup_home
make_stub ':'
printf '{"version":3,"skills":{"seeded":{"source":"example/repo"},"ghost":{"source":"example/repo"}}}\n' \
  >"$FAKE_HOME/.agents/.skill-lock.json"
snap >"$TMP/f.before"
PATH="$TMP/bin:$PATH" "$GUARD" skills add example/repo --skill webapp-demo -g -y >"$TMP/f.log" 2>&1
rc=$?
snap >"$TMP/f.after"
assert "case F exit 0"                          "[ $rc -eq 0 ]"
assert "case F removed the stray record"        "[ ! -e '$FAKE_HOME/.agents/.skill-lock.json' ]"
assert "case F folded it into the roster"       "grep -q '\"seeded\"' '$FAKE_HOME/.agents/available-skills/.skill-lock.json'"
assert "case F dropped the entry with no folder" "! grep -q ghost '$FAKE_HOME/.agents/available-skills/.skill-lock.json'"
assert "case F no writes outside"               "[ -z \"\$(comm -13 '$TMP/f.before' '$TMP/f.after')\" ]"

# Case E: the real machine. Read-only. Only reached through this test's own
# entry point, so REAL_HOME is captured before any fixture rewrites HOME — the
# audit must describe the machine, not the last scratch home.
real_agents="${REAL_AGENTS_HOME:-$REAL_HOME/.agents}"
real_available="$real_agents/available-skills"
if [ -d "$real_available" ]; then
  avail_real="$(cd "$real_available" && pwd -P)"
  assert "live: auditing the real home" "[ '$REAL_HOME' != '$FAKE_HOME' ]"
  copies=""
  for r in "$REAL_HOME"/.claude/skills "$REAL_HOME"/.codex/skills "$REAL_HOME"/.cursor/skills \
           "$REAL_HOME"/.grok/skills "$REAL_HOME"/.gemini/skills "$REAL_HOME"/.config/opencode/skills; do
    [ -d "$r" ] || continue
    # A harness root that IS available-skills (e.g. ~/.grok/skills -> available-skills)
    # is the one real tree seen through another name; its entries are not copies.
    [ "$(cd "$r" && pwd -P)" = "$avail_real" ] && continue
    for p in "$r"/*; do
      [ -e "$p" ] || continue
      [ -L "$p" ] && continue
      [ -e "$real_available/$(basename "$p")" ] && copies="$copies $p"
    done
  done
  assert "live: no real skill copy outside available-skills" "[ -z '$copies' ]"
  assert "live: ~/.agents/skills reaches available-skills" \
    "[ ! -e '$real_agents/skills' ] || [ \"\$(cd '$real_agents' && readlink -f skills)\" = \"\$avail_real\" ]"
  assert "live: no install record at ~/.agents/.skill-lock.json" "[ ! -e '$real_agents/.skill-lock.json' ]"
else
  echo "skip - live audit: no $real_available on this machine"
fi

if [ "$fail" -ne 0 ]; then
  echo "FAILED: global aubx installs are not confined to available-skills"
  exit 1
fi
echo "global aubx installs write only to available-skills"
