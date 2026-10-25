#!/usr/bin/env bash
# Proves skills-add works when ~/.agents/skills is a symlink to available-skills:
# the install still has to be seen as new, the harness link the installer made has
# to go, and a link that was already there must stay.
set -euo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/skills-add"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$TMP/bin"
ln -s available-skills "$AGENTS_HOME/skills"

# A link the user curated before this run: it resolves, and it is not ours to drop.
mkdir -p "$AGENTS_HOME/available-skills/curated"
printf -- '---\nname: curated\n---\n' >"$AGENTS_HOME/available-skills/curated/SKILL.md"
ln -s "$AGENTS_HOME/skills/curated" "$HOME/.codex/skills/curated"

cat >"$TMP/bin/npx" <<'STUB'
#!/usr/bin/env bash
name=""
prev=""
for a in "$@"; do
  [ "$prev" = "--skill" ] && name="$a"
  prev="$a"
done
[ -n "$name" ] || { echo "stub: no --skill given" >&2; exit 1; }
mkdir -p "$AGENTS_HOME/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$AGENTS_HOME/skills/$name/SKILL.md"
ln -sfn "../../.agents/skills/$name" "$HOME/.claude/skills/$name"
STUB
chmod +x "$TMP/bin/npx"

PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo-skill -g -y

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }
assert "skill landed in available-skills"  "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "skill visible through the link"    "[ -f \"$AGENTS_HOME/skills/demo-skill/SKILL.md\" ]"
assert "installer harness link removed"    "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"
assert "pre-existing curated link kept"    "[ -L \"$HOME/.codex/skills/curated\" ]"
exit "$fail"
