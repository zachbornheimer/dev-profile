#!/usr/bin/env bash
# Proves aubx-skills installs through aubx and leaves no write outside
# $AGENTS_HOME/available-skills. Uses stubs, so it needs no network or aube.
set -euo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

# Stub `aubx <...> skills add <...>`: writes exactly like the real installer —
# skill folder under $HOME/.agents/skills, harness symlink, global lock.
make_stub() {
  cat >"$1" <<'STUB'
#!/usr/bin/env bash
# aubx skills add <pkg> [-g] [--skill NAME] [...]
args=("$@"); [ "${args[0]:-}" = skills ] && shift
[ "${1:-}" = add ] && shift
name=""; prev=""
for a in "$@"; do [ "$prev" = "--skill" ] && name="$a"; prev="$a"; done
[ -n "$name" ] || { echo "stub aubx: no --skill given" >&2; exit 1; }
mkdir -p "$HOME/.agents/skills/$name" "$HOME/.claude/skills"
printf -- '---\nname: %s\n---\n' "$name" >"$HOME/.agents/skills/$name/SKILL.md"
ln -sfn "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name"
printf '{"version":3,"skills":{}}' >"$HOME/.agents/.skill-lock.json"
STUB
  chmod +x "$1"
}

# ---- scenario 1: ~/.agents/skills is a real auto-scan dir -> relocation ----
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home/.agents/skills/typesafe-ai" "$TMP/home/.claude/skills" "$TMP/bin" "$TMP/scratch"
touch "$TMP/home/.agents/skills/typesafe-ai/SKILL.md"
make_stub "$TMP/bin/aubx"

HOME="$TMP/home" AGENTS_HOME="$TMP/home/.agents" PATH="$TMP/bin:$PATH" TMPDIR="$TMP/scratch" \
  "$WRAPPER" example/repo --skill demo
H="$TMP/home/.agents"
assert "skill installed into available-skills" "[ -f \"$H/available-skills/demo/SKILL.md\" ]"
assert "auto-scan dir untouched"               "[ ! -e \"$H/skills/demo\" ]"
assert "typesafe-ai untouched"                 "[ -f \"$H/skills/typesafe-ai/SKILL.md\" ]"
assert "no harness symlink left behind"        "[ ! -e \"$TMP/home/.claude/skills/demo\" ] && [ ! -L \"$TMP/home/.claude/skills/demo\" ]"
assert "sandbox removed"                       "[ -z \"$(ls -A "$TMP/scratch")\" ]"
rm -rf "$TMP"; trap - EXIT

# ---- scenario 2: ~/.agents/skills -> available-skills (live machine state) ----
# The installer writes straight into available-skills. The wrapper must NOT
# try to move the folder onto itself, and must NOT delete it.
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home/.agents/available-skills" "$TMP/home/.claude/skills" "$TMP/bin" "$TMP/scratch"
ln -s available-skills "$TMP/home/.agents/skills"
make_stub "$TMP/bin/aubx"

set +e
HOME="$TMP/home" AGENTS_HOME="$TMP/home/.agents" PATH="$TMP/bin:$PATH" TMPDIR="$TMP/scratch" \
  "$WRAPPER" example/repo --skill demo2 >"$TMP/out.txt" 2>&1
rc=$?
set -e
H="$TMP/home/.agents"
assert "symlinked scan dir: exit 0"            "[ $rc -eq 0 ]"
assert "symlinked scan dir: skill survives"    "[ -f \"$H/available-skills/demo2/SKILL.md\" ]"
assert "symlinked scan dir: not deleted"       "[ -d \"$H/available-skills/demo2\" ]"

exit "$fail"
