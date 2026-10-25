#!/usr/bin/env bash
# Proves aubx-skills hands the installer a warm package store: the throwaway HOME
# links the caller's aube cache and data trees instead of growing cold copies, so
# an install reuses what is already on disk. Also proves an absent store is not
# an error. In both cases the only durable write stays inside available-skills.
set -uo pipefail

WRAPPER="${WRAPPER:-$(cd "$(dirname "$0")/.." && pwd)/aubx-skills}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/skills/typesafe-ai" "$HOME/.claude/skills" "$TMP/bin"
printf -- '---\nname: typesafe-ai\n---\n' >"$AGENTS_HOME/skills/typesafe-ai/SKILL.md"

# The caller's package state. Each tree carries a marker so the stub can prove
# the child read the real store and not an empty scratch copy.
CACHE="$HOME/.cache/aube"
DATA="$HOME/.local/share/aube"
mkdir -p "$CACHE" "$DATA"
printf 'cache\n' >"$CACHE/marker"
printf 'data\n' >"$DATA/marker"

# Stand-in for `aubx skills add -g`: mimics the real installer, which derives
# every path from $HOME and links every detected agent. It records what the
# child saw — the resolved target of each package-state path and its marker —
# at the absolute path in $PROBE.
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
{
  printf 'cache=%s\n' "$(readlink "$HOME/.cache/aube" 2>/dev/null || true)"
  printf 'data=%s\n' "$(readlink "$HOME/.local/share/aube" 2>/dev/null || true)"
  printf 'cachemarker=%s\n' "$(cat "$HOME/.cache/aube/marker" 2>/dev/null || true)"
  printf 'datamarker=%s\n' "$(cat "$HOME/.local/share/aube/marker" 2>/dev/null || true)"
} >"$PROBE"
mkdir -p "$HOME/.agents/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$HOME/.agents/skills/$name/SKILL.md"
printf -- '{"version":3,"skills":{"%s":{"source":"example/repo"}}}\n' "$name" >"$HOME/.agents/.skill-lock.json"
mkdir -p "$HOME/.claude/skills"
ln -sfn "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name"
STUB
chmod +x "$TMP/bin/aubx"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

# --- warm store: the child must resolve each path to the caller's real tree ---
PATH="$TMP/bin:$PATH" PROBE="$TMP/probe-warm.txt" "$WRAPPER" example/repo --skill demo-skill -y >"$TMP/run-warm.log" 2>&1
rc=$?

assert "warm: exited 0"                  "[ $rc -eq 0 ]"
assert "warm: cache link is the real tree" "grep -Fxq 'cache=$CACHE' '$TMP/probe-warm.txt'"
assert "warm: data link is the real tree"  "grep -Fxq 'data=$DATA' '$TMP/probe-warm.txt'"
assert "warm: child read the cache marker" "grep -Fxq 'cachemarker=cache' '$TMP/probe-warm.txt'"
assert "warm: child read the data marker"  "grep -Fxq 'datamarker=data' '$TMP/probe-warm.txt'"
assert "warm: caller cache stayed a real dir" "[ -d \"$CACHE\" ] && [ ! -L \"$CACHE\" ] && [ -f \"$CACHE/marker\" ]"
assert "warm: caller data stayed a real dir"  "[ -d \"$DATA\" ] && [ ! -L \"$DATA\" ] && [ -f \"$DATA/marker\" ]"
assert "warm: skill folder in available-skills" "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "warm: nothing new in auto-scan dir" "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ] && [ -f \"$AGENTS_HOME/skills/typesafe-ai/SKILL.md\" ]"
assert "warm: no ~/.agents/.skill-lock.json" "[ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
assert "warm: no harness link in ~/.claude/skills" "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"
assert "warm: claimed clean scope" "grep -q 'no writes outside' '$TMP/run-warm.log'"

# --- absent store: no cache tree to borrow is not a failure ---
rm -rf "$CACHE"
PATH="$TMP/bin:$PATH" PROBE="$TMP/probe-absent.txt" "$WRAPPER" example/repo --skill absent-skill -y >"$TMP/run-absent.log" 2>&1
rc_absent=$?

assert "absent: exited 0"                 "[ $rc_absent -eq 0 ]"
assert "absent: no cache link invented"   "grep -Fxq 'cache=' '$TMP/probe-absent.txt'"
assert "absent: absent cache not created" "[ ! -e \"$CACHE\" ]"
assert "absent: data still linked"        "grep -Fxq 'data=$DATA' '$TMP/probe-absent.txt'"
assert "absent: datamarker readable"      "grep -Fxq 'datamarker=data' '$TMP/probe-absent.txt'"
assert "absent: skill folder in available-skills" "[ -f \"$AGENTS_HOME/available-skills/absent-skill/SKILL.md\" ]"
assert "absent: no ~/.agents/.skill-lock.json" "[ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
assert "absent: claimed clean scope"      "grep -q 'no writes outside' '$TMP/run-absent.log'"

exit "$fail"
