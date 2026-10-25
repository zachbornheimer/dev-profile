#!/usr/bin/env bash
# Proves the scope guard covers every launcher that reaches the vercel `skills`
# installer, not just the one named `aubx`. `aube skills add` runs the same
# package through dlx, and the `skills` CLI installs directly; both derive their
# paths from $HOME and write ~/.agents/skills, a link per harness, and
# ~/.agents/.skill-lock.json.
#
# Each entry point must route a global add/update/upgrade into aubx-skills, pass
# an explicit -p/--project install through, and leave every other subcommand
# untouched. The `skills` shim must refuse rather than install unconfined when
# the confiner is missing.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_SHIM="${SKILLS_SHIM:-$HOME/.local/bin/skills}"
[ -x "$SKILLS_SHIM" ] || { echo "FAIL - no skills shim at $SKILLS_SHIM"; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
GUARD="$AGENTS_HOME/bin"
REAL="$TMP/real"
mkdir -p "$GUARD" "$REAL" "$AGENTS_HOME/skills/typesafe-ai" "$HOME/.claude/skills"
touch "$AGENTS_HOME/skills/typesafe-ai/SKILL.md"

cp "$SELF_DIR/aube" "$GUARD/aube"
cp "$SKILLS_SHIM" "$GUARD/skills"
chmod +x "$GUARD/aube" "$GUARD/skills"

# Real-CLI stand-ins: record argv and mimic the installer's writes — a folder in
# the auto-scan dir plus a harness link, exactly like a global install does.
stub() {
  cat >"$REAL/$1" <<STUB
#!/usr/bin/env bash
printf '%s\\n' "\$*" >>"\$HOME/argv-$1.log"
case "\${1:-}" in skills) shift ;; esac
case "\${1:-}" in
  add|update|upgrade) ;;
  *) echo passthrough; exit 0 ;;
esac
name=""; prev=""
for a in "\$@"; do [ "\$prev" = "--skill" ] && name="\$a"; prev="\$a"; done
[ -n "\$name" ] || name=unnamed
mkdir -p "\$AGENTS_HOME/skills/\$name"
printf -- '---\\nname: %s\\n---\\n' "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
ln -sfn "\$AGENTS_HOME/skills/\$name" "\$HOME/.claude/skills/\$name"
STUB
  chmod +x "$REAL/$1"
}
stub aube
stub skills
# The shim prefers `aubx` as its read launcher (npx cannot run this package on
# this machine), so the stand-in environment must model that chain too: record
# argv, strip the `skills` prefix exactly like the real guard's passthrough, and
# exec the real-CLI stand-in. Without it the shim's aubx route reaches the live
# machine's real guard through the ambient PATH, the stub CLI never runs, and
# the passthrough assertions test nothing. test_skills_shim_confinement.sh
# documents the same lesson for the confiner's launcher.
cat >"$REAL/aubx" <<STUB
#!/usr/bin/env bash
printf '%s\\n' "\$*" >>"\$HOME/argv-aubx.log"
if [ "\${1:-}" = skills ]; then shift; fi
exec "$REAL/skills" "\$@"
STUB
chmod +x "$REAL/aubx"
# The skills shim answers reads through the AGENTS_HOME-derived guard
# ($AGENTS_HOME/bin/aubx), never a PATH lookup, so the stand-in guard must also
# live where the shim will execute it. Same stub, mirrored to the one owned
# location; without it a list-only add refuses with 127 instead of passing
# through, and the assertion below tests nothing.
cp "$REAL/aubx" "$GUARD/aubx"

# Confiner stand-in in the guard's own dir: records argv, writes only into the roster.
cat >"$GUARD/aubx-skills" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$HOME/confined.log"
name=""; prev=""
for a in "$@"; do [ "$prev" = "--skill" ] && name="$a"; prev="$a"; done
[ -n "$name" ] || name=unnamed
mkdir -p "$AGENTS_HOME/available-skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$AGENTS_HOME/available-skills/$name/SKILL.md"
STUB
chmod +x "$GUARD/aubx-skills"

aube() { PATH="$GUARD:$REAL:$PATH" "$GUARD/aube" "$@"; }
skills() { PATH="$GUARD:$REAL:$PATH" "$GUARD/skills" "$@"; }

# --- aube -------------------------------------------------------------------
aube skills add example/repo --skill a1 -g -y >"$TMP/a.log" 2>&1
assert "aube: global add routed to confiner" "grep -q 'skills add example/repo --skill a1 -g -y' \"\$HOME/confined.log\""
assert "aube: global add never hit real aube" "[ ! -f \"\$HOME/argv-aube.log\" ]"
assert "aube: content only in roster" "[ -f \"\$AGENTS_HOME/available-skills/a1/SKILL.md\" ]"
assert "aube: nothing in auto-scan dir" "[ ! -e \"\$AGENTS_HOME/skills/a1\" ]"
assert "aube: no harness link" "[ ! -e \"\$HOME/.claude/skills/a1\" ]"

aube skills add example/repo --skill a2 -y >"$TMP/b.log" 2>&1
assert "aube: add without -g is confined" "grep -q 'a2' \"\$HOME/confined.log\""
assert "aube: add without -g left no harness link" "[ ! -e \"\$HOME/.claude/skills/a2\" ]"

aube skills update -g a1 >"$TMP/c.log" 2>&1
assert "aube: global update is confined" "grep -q 'skills update -g a1' \"\$HOME/confined.log\""

aube skills add example/repo --skill a3 -p -y >"$TMP/d.log" 2>&1
assert "aube: explicit project add passes through" "grep -q 'skills add example/repo --skill a3 -p -y' \"\$HOME/argv-aube.log\""

aube install >"$TMP/e.log" 2>&1
assert "aube: install passes through" "grep -qx 'install' \"\$HOME/argv-aube.log\""

# --- skills -----------------------------------------------------------------
rm -f "$HOME/confined.log" "$HOME/argv-skills.log"
skills add example/repo --skill s1 -g -y >"$TMP/f.log" 2>&1
assert "skills: global add routed to confiner" "grep -q 'skills add example/repo --skill s1 -g -y' \"\$HOME/confined.log\""
assert "skills: global add never hit real CLI" "[ ! -f \"\$HOME/argv-skills.log\" ]"
assert "skills: content only in roster" "[ -f \"\$AGENTS_HOME/available-skills/s1/SKILL.md\" ]"
assert "skills: nothing in auto-scan dir" "[ ! -e \"\$AGENTS_HOME/skills/s1\" ]"
assert "skills: no harness link" "[ ! -e \"\$HOME/.claude/skills/s1\" ]"

skills add example/repo --skill s2 -y >"$TMP/g.log" 2>&1
assert "skills: add without -g is confined" "grep -q 's2' \"\$HOME/confined.log\""
assert "skills: add without -g left no harness link" "[ ! -e \"\$HOME/.claude/skills/s2\" ]"

skills update >"$TMP/h.log" 2>&1
assert "skills: bare update is confined" "grep -qx 'skills update' \"\$HOME/confined.log\""

skills list -g >"$TMP/i.log" 2>&1
assert "skills: list passes through" "grep -qx 'list -g' \"\$HOME/argv-skills.log\""

skills add example/repo --skill s3 -p -y >"$TMP/j.log" 2>&1
assert "skills: explicit project add passes through" "grep -q 'add example/repo --skill s3 -p -y' \"\$HOME/argv-skills.log\""

# `add -l`/`--list` lists what a repo offers and installs nothing, so there is
# no write set to confine: it must reach the real CLI, not the confiner. This
# mirrors the aubx guard's list-only passthrough.
skills add example/repo -l >"$TMP/n.log" 2>&1
assert "skills: add --list passes through" "grep -q 'add example/repo -l' \"\$HOME/argv-skills.log\""

# Removal is a write: it deletes a roster folder, the harness links to it, and
# its record entry. Both entry points must route it through the confiner.
rm -f "$HOME/confined.log" "$HOME/argv-skills.log"
skills remove s1 -g -y >"$TMP/l.log" 2>&1
assert "skills: global remove routed to confiner" "grep -q 'skills remove s1 -g -y' \"\$HOME/confined.log\""
assert "skills: global remove never hit real CLI" "! grep -q 'skills remove s1' \"\$HOME/argv-skills.log\""

rm -f "$HOME/confined.log" "$HOME/argv-aube.log"
aube skills remove a1 -g -y >"$TMP/m.log" 2>&1
assert "aube: global remove routed to confiner" "grep -q 'skills remove a1 -g -y' \"\$HOME/confined.log\""
assert "aube: global remove never hit real aube" "! grep -q 'skills remove a1' \"\$HOME/argv-aube.log\""

# A missing confiner must refuse: falling through to the unconfined CLI is the
# leak this whole shim exists to prevent.
mv "$GUARD/aubx-skills" "$TMP/aubx-skills.off"
skills add example/repo --skill s4 -g -y >"$TMP/k.log" 2>&1
rc=$?
assert "skills: refuses when confiner is missing" "[ $rc -eq 127 ]"
assert "skills: refusal wrote nothing" "[ ! -e \"\$AGENTS_HOME/skills/s4\" ] && [ ! -e \"\$HOME/.claude/skills/s4\" ]"
mv "$TMP/aubx-skills.off" "$GUARD/aubx-skills"

assert "no ~/.agents/.skill-lock.json" "[ ! -f \"\$AGENTS_HOME/.skill-lock.json\" ]"

if [ "$fail" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "all entry points confine global installs to available-skills"
