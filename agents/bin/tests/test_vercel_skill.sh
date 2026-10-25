#!/usr/bin/env bash
# Proves vercel-skill installs a Vercel skill and leaves it in
# $AGENTS_HOME/available-skills: the caller's cwd stays clean, the auto-scan dir keeps
# no copy, the harness link the installer made is dropped, a reinstall does not nest a
# second copy, and a failed install exits non-zero with nothing left behind.
#
# Offline: a stub `npx` stands in for the Skills CLI and installs the way the real one
# does, into the scan dir plus a harness symlink. The real `skills-add` does the
# relocating, so the move path is exercised, not mocked.
set -euo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$BIN/vercel-skill"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
export CALLS="$TMP/calls"
: >"$CALLS"
mkdir -p "$AGENTS_HOME/skills" "$AGENTS_HOME/available-skills" "$HOME/.claude/skills" "$TMP/cwd" "$TMP/bin"

cat >"$TMP/bin/npx" <<'STUB'
#!/usr/bin/env bash
# Stand-in for `npx -y skills@latest add <pkg> --skill <name> -g -y`: records the call,
# installs into the scan dir, links into a harness dir — the real CLI's behaviour.
set -euo pipefail
printf '%s\n' "$*" >>"$CALLS"
[ "${1:-}" = "-y" ] && shift
[ "${1:-}" = "skills@latest" ] || { printf 'stub: unexpected npx call: %s\n' "$*" >&2; exit 64; }
shift
[ "${1:-}" = "add" ] || { printf 'stub: unexpected skills command: %s\n' "$*" >&2; exit 64; }
shift; pkg="$1"; shift
skill=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --skill | -s) skill="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$skill" ] || { printf 'stub: no --skill given\n' >&2; exit 64; }
mkdir -p "$AGENTS_HOME/skills/$skill/references"
if [ "$skill" != hollow-skill ]; then
  printf -- '---\nname: %s\n---\n' "$skill" >"$AGENTS_HOME/skills/$skill/SKILL.md"
fi
printf 'ref\n' >"$AGENTS_HOME/skills/$skill/references/r.md"
ln -sfn "$AGENTS_HOME/skills/$skill" "$HOME/.claude/skills/$skill"
printf '{"version":3,"skills":{"%s":{"package":"%s"}}}\n' "$skill" "${pkg##*/}" >"$AGENTS_HOME/.skill-lock.json"
STUB
chmod +x "$TMP/bin/npx"
export PATH="$TMP/bin:$BIN:$PATH"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

cd "$TMP/cwd"
"$WRAPPER" demo-skill >/dev/null 2>&1
assert "installed skill parked at available-skills/<name>/SKILL.md" \
  "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "subdirectories survive the move" \
  "[ -f \"$AGENTS_HOME/available-skills/demo-skill/references/r.md\" ]"
assert "nothing written to caller cwd" "[ -z \"$(ls -A "$TMP/cwd")\" ]"
assert "auto-scan dir keeps no real copy" "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ]"
assert "harness link the installer made is dropped" \
  "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"
assert "install ran the Skills CLI, global and unattended" \
  "grep -qx -- '-y skills@latest add vercel-labs/agent-skills --skill demo-skill -g -y' \"$CALLS\""
assert "install record ends up in the roster" \
  "[ -f \"$AGENTS_HOME/available-skills/.skill-lock.json\" ] && [ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"

"$WRAPPER" demo-skill >/dev/null 2>&1
assert "reinstall keeps one copy" \
  "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ] && [ ! -e \"$AGENTS_HOME/available-skills/demo-skill/demo-skill\" ]"
assert "reinstall leaves the auto-scan dir clean" "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ]"

# vercel-cli ships from vercel/vercel, not some other repo.
"$WRAPPER" vercel-cli >/dev/null 2>&1
assert "vercel-cli lands under its own name" \
  "[ -f \"$AGENTS_HOME/available-skills/vercel-cli/SKILL.md\" ]"
assert "vercel-cli is fetched from vercel/vercel" \
  "grep -q -- 'add vercel/vercel --skill vercel-cli' \"$CALLS\""

# A folder with no SKILL.md is not a skill: it must fail and not be left behind.
if "$WRAPPER" hollow-skill >/dev/null 2>"$TMP/hollow.err"; then
  echo "FAIL - a folder without SKILL.md should exit non-zero"; fail=1
else
  echo "ok   - a folder without SKILL.md exits non-zero"
fi
assert "the failure names the missing SKILL.md" "grep -q 'no SKILL.md' \"$TMP/hollow.err\""
assert "the failure leaves no folder behind" "[ ! -e \"$AGENTS_HOME/available-skills/hollow-skill\" ]"

if "$WRAPPER" ../escape >/dev/null 2>&1; then
  echo "FAIL - a path should be rejected"; fail=1
else
  echo "ok   - a path is rejected"
fi
assert "a rejected path never reaches the installer" "! grep -q 'escape' \"$CALLS\""

exit "$fail"
