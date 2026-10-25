#!/usr/bin/env bash
# Proves skills-add leaves the installer's install record inside the roster:
# `skills add -g` writes $AGENTS_HOME/.skill-lock.json, a file outside
# available-skills; the wrapper must merge it into the roster's record and drop
# the outside copy, so available-skills is the only durable write.
set -euo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/skills-add"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$HOME/.claude/skills" "$TMP/bin"
ln -s available-skills "$AGENTS_HOME/skills"

# Stand-in for `npx skills add -g`: writes what the real CLI writes, including
# the install record at $AGENTS_HOME/.skill-lock.json.
cat >"$TMP/bin/npx" <<'STUB'
#!/usr/bin/env bash
name=""; prev=""
for a in "$@"; do
  [ "$prev" = "--skill" ] && name="$a"
  prev="$a"
done
[ -n "$name" ] || { echo "stub: no --skill given" >&2; exit 1; }
mkdir -p "$AGENTS_HOME/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$AGENTS_HOME/skills/$name/SKILL.md"
ln -sfn "../../.agents/skills/$name" "$HOME/.claude/skills/$name"
record="$AGENTS_HOME/.skill-lock.json"
if [ -f "$record" ]; then
  jq -c --arg n "$name" '.skills[$n]={source:"demo/repo",sourceType:"github",skillPath:("skills/"+$n+"/SKILL.md")}' "$record" >"$record.tmp"
else
  jq -cn --arg n "$name" '{version:3,skills:{($n):{source:"demo/repo",sourceType:"github",skillPath:("skills/"+$n+"/SKILL.md")}},dismissed:{}}' >"$record.tmp"
fi
mv "$record.tmp" "$record"
STUB
chmod +x "$TMP/bin/npx"

PATH="$TMP/bin:$PATH" "$WRAPPER" demo/repo --skill demo-skill -g -y >/dev/null

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }
assert "skill landed in the roster"       "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "no install record outside roster" "[ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
assert "record kept inside the roster"    "grep -q demo-skill \"$AGENTS_HOME/available-skills/.skill-lock.json\""
assert "harness link removed"             "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"

# A second install must merge into the roster's record, not replace it.
PATH="$TMP/bin:$PATH" "$WRAPPER" demo/repo --skill second-skill -g -y >/dev/null
assert "second install merged into record" \
  "grep -q demo-skill \"$AGENTS_HOME/available-skills/.skill-lock.json\" && grep -q second-skill \"$AGENTS_HOME/available-skills/.skill-lock.json\""
exit "$fail"
