#!/usr/bin/env bash
# Proves skills-add leaves every non-kept skill in the roster:
#   1. a fresh install is moved out of the auto-scan dir,
#   2. a reinstall that updates a skill already in the scan dir is still moved,
#   3. under the unified layout (skills -> available-skills) it reports where the
#      skill landed and never copies/moves a folder onto itself.
set -euo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/skills-add"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/skills/typesafe-ai" "$HOME/.claude/skills" "$TMP/bin"
touch "$AGENTS_HOME/skills/typesafe-ai/SKILL.md"

# Stand-in for `npx skills add`: mimics the real installer's two effects.
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
ln -sfn "../../.agents/skills/$name" "$HOME/.claude/skills/$name"
STUB
chmod +x "$TMP/bin/npx"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

# 1. fresh install
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo-skill -g -y >/dev/null
assert "skill moved into available-skills" "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "skill gone from auto-scan dir"      "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ]"
assert "typesafe-ai untouched"              "[ -f \"$AGENTS_HOME/skills/typesafe-ai/SKILL.md\" ]"
assert "dangling claude link removed"       "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"

# 2. reinstall that updates a skill the scan dir already contained: no new
#    directory appears, so a before/after diff alone cannot see it.
STUB_REVISION=2 PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo-skill -g -y >/dev/null
assert "updated skill relocated"  "grep -q 'revision: 2' \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\""
assert "update left scan dir clear" "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ]"

# 2b. An entry can be gone by the time the wrapper handles it: the installer
#     removes its own temporary links on exit, and a concurrent run may relocate
#     the same name first. A vanished source must not abort the run, and the
#     dangling link it leaves behind must not survive.
ln -s /nonexistent/ghost "$AGENTS_HOME/skills/zz-ghost"
status=0
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill after-ghost -g -y >/dev/null 2>&1 ||
  status=$?
assert "vanished entry does not fail the run" "[ $status -eq 0 ]"
assert "skill arriving beside a vanished entry is relocated" \
  "[ -f \"$AGENTS_HOME/available-skills/after-ghost/SKILL.md\" ]"
assert "dangling entry dropped from the scan dir" \
  "[ ! -L \"$AGENTS_HOME/skills/zz-ghost\" ] && [ ! -e \"$AGENTS_HOME/skills/zz-ghost\" ]"
assert "harness link still removed when an entry vanished" \
  "[ ! -L \"$HOME/.claude/skills/after-ghost\" ]"

# 3. unified layout: the auto-scan dir IS the roster.
rm -rf "$AGENTS_HOME/skills"
ln -s available-skills "$AGENTS_HOME/skills"
# shellcheck disable=SC2034 # read by the eval'd assert condition below
out="$(PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill unified-skill -g -y 2>&1)"
assert "unified: skill kept in the roster" "[ -f \"$AGENTS_HOME/available-skills/unified-skill/SKILL.md\" ]"
assert "unified: skill reachable via scan path" "[ -f \"$AGENTS_HOME/skills/unified-skill/SKILL.md\" ]"
assert "unified: result reported, not denied" \
  "printf '%s' \"\$out\" | grep -q 'unified-skill.*available-skills'"
assert "unified: does not claim nothing happened" \
  "! printf '%s' \"\$out\" | grep -q 'nothing new to relocate'"

exit "$fail"
