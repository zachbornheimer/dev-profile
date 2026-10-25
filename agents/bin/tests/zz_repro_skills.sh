#!/usr/bin/env bash
# Proves aubx-skills' contract: the installer runs under a throwaway HOME, so
# its skill folder, its per-agent links and its .skill-lock.json all land in
# scratch. The only real write is the skill folder copied into
# ~/.agents/available-skills.
set -uo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
TMP="$(mktemp -d)"
echo TMP=$TMP

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/skills/typesafe-ai" "$HOME/.claude/skills" "$TMP/bin"
printf -- '---\nname: typesafe-ai\n---\n' >"$AGENTS_HOME/skills/typesafe-ai/SKILL.md"

# Stand-in for `aubx skills add -g`: mimics the real installer, which derives
# every path from $HOME and links every detected agent.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
[ "$1" = "skills" ] && [ "$2" = "add" ] || { echo "stub: bad invocation: $*" >&2; exit 1; }
case " $* " in *" -g "*|*" --global "*) ;; *) echo "stub: global flag missing" >&2; exit 1 ;; esac
name=""; prev=""
for a in "$@"; do
  [ "$prev" = "--skill" ] && name="$a"
  prev="$a"
done
[ -n "$name" ] || { echo "stub: no --skill given" >&2; exit 1; }
mkdir -p "$HOME/.agents/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$HOME/.agents/skills/$name/SKILL.md"
printf -- '{"version":3,"skills":{"%s":{"source":"example/repo"}}}\n' "$name" >"$HOME/.agents/.skill-lock.json"
mkdir -p "$HOME/.claude/skills"
ln -sfn "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name"
STUB
chmod +x "$TMP/bin/aubx"

PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo-skill -y >"$TMP/run.log" 2>&1
rc=$?

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

assert "exited 0"                    "[ $rc -eq 0 ]"
assert "real folder in available-skills" "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "available-skills entry is a real dir" "[ -d \"$AGENTS_HOME/available-skills/demo-skill\" ] && [ ! -L \"$AGENTS_HOME/available-skills/demo-skill\" ]"
assert "installer ran under scratch HOME" "grep -q 'isolated HOME=' '$TMP/run.log'"
assert "nothing new in auto-scan dir" "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ] && [ ! -L \"$AGENTS_HOME/skills/demo-skill\" ]"
assert "no ~/.agents/.skill-lock.json" "[ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
assert "no harness link in ~/.claude/skills" "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"
assert "typesafe-ai untouched"       "[ -f \"$AGENTS_HOME/skills/typesafe-ai/SKILL.md\" ]"
assert "record kept inside available-skills" "grep -q demo-skill '$AGENTS_HOME/available-skills/.skill-lock.json'"

# Second run must stay green and stay out of the rest of the home.
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo-skill -y >"$TMP/run2.log" 2>&1
rc2=$?
assert "second run exits 0"          "[ $rc2 -eq 0 ]"
assert "second run still no lock outside" "grep -q 'no writes outside' '$TMP/run2.log' && [ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
exit "$fail"
