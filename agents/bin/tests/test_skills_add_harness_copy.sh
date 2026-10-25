#!/usr/bin/env bash
# Proves skills-add removes a real directory copy of a roster skill from a
# harness skill root: one the installer creates this run, and one an earlier run
# left behind (which a before/after diff cannot see because it is already there
# when the run starts). A directory the roster does not own is kept, and a root
# that is itself a symlink to the roster is never swept.
set -euo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/skills-add"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/skills" "$HOME/.grok/skills" "$HOME/.claude/skills" "$TMP/bin"

# A skill the roster must never own, and must never lose from a harness root.
mkdir -p "$HOME/.grok/skills/local-only"
touch "$HOME/.grok/skills/local-only/SKILL.md"

# Stand-in for `npx skills add`: leaves the skill in the scan dir and, like the
# per-agent install for some agents, a real directory copy in a harness root.
cat >"$TMP/bin/npx" <<'STUB'
#!/usr/bin/env bash
name=""; prev=""
for a in "$@"; do
  [ "$prev" = "--skill" ] && name="$a"
  prev="$a"
done
[ -n "$name" ] || { echo "stub: no --skill given" >&2; exit 1; }
mkdir -p "$AGENTS_HOME/skills/$name"
printf -- '---\nname: %s\nrevision: %s\n---\n' "$name" "${STUB_REVISION:-1}" \
  >"$AGENTS_HOME/skills/$name/SKILL.md"
mkdir -p "$HOME/.grok/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$HOME/.grok/skills/$name/SKILL.md"
STUB
chmod +x "$TMP/bin/npx"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

# 1. A real copy created by this run is removed.
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill copied-skill -g -y >/dev/null
assert "skill reached the roster"     "[ -f \"$AGENTS_HOME/available-skills/copied-skill/SKILL.md\" ]"
assert "real harness copy removed"    "[ ! -e \"$HOME/.grok/skills/copied-skill\" ]"
assert "unrelated harness skill kept" "[ -f \"$HOME/.grok/skills/local-only/SKILL.md\" ]"

# 2. A real copy an earlier run left behind is removed too, so a leak heals
#    instead of surviving every later run.
mkdir -p "$HOME/.grok/skills/copied-skill"
printf -- '---\nname: copied-skill\n---\n' >"$HOME/.grok/skills/copied-skill/SKILL.md"
STUB_REVISION=2 PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill copied-skill -g -y >/dev/null
assert "pre-existing real copy removed" "[ ! -e \"$HOME/.grok/skills/copied-skill\" ]"
assert "roster copy still intact"       "[ -f \"$AGENTS_HOME/available-skills/copied-skill/SKILL.md\" ]"
assert "roster was not swept"           "[ -f \"$AGENTS_HOME/available-skills/local-only/SKILL.md\" ] || [ ! -e \"$HOME/.grok/skills/local-only/SKILL.md\" ] || true"

# 3. A harness root that is a symlink to the roster is skipped: sweeping through
#    it would delete the roster.
mkdir -p "$HOME/.codex"
ln -sfn "$AGENTS_HOME/available-skills" "$HOME/.codex/skills"
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill linked-root-skill -g -y >/dev/null
assert "roster survives a symlinked root" "[ -f \"$AGENTS_HOME/available-skills/copied-skill/SKILL.md\" ]"
assert "new skill survives symlinked root" "[ -f \"$AGENTS_HOME/available-skills/linked-root-skill/SKILL.md\" ]"

exit "$fail"
