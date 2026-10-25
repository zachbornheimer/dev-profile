#!/usr/bin/env bash
# Proves the `skills` shim confines a global install to the roster, end to end,
# through the mechanism that actually runs on this machine:
#
#   ~/.local/bin/skills  ->  $AGENTS_HOME/bin/aubx-skills  ->  real CLI under a
#   throwaway HOME                                          ->  copy into
#                                                               available-skills
#
# The fake installer is an `aubx` on PATH (not an `npx`), because aubx-skills
# resolves the real CLI as `aubx` and hands it `skills <verb>`. An earlier
# version of this test stubbed `npx`, which the confiner never invokes, so it
# "failed" while the confinement was intact — a test lying about the system is
# worse than no test.
set -uo pipefail

SHIM="${SHIM:-$HOME/.local/bin/skills}"
CONFINER_SRC="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

[ -x "$SHIM" ] || { echo "FAIL - no shim at $SHIM"; exit 1; }
[ -x "$CONFINER_SRC" ] || { echo "FAIL - no confiner at $CONFINER_SRC"; exit 1; }

# A sandbox machine: its own HOME, its own AGENTS_HOME, its own confiner.
# The confiner is linked into the sandbox so the shim resolves *this* one
# (CONFINER = $AGENTS_HOME/bin/aubx-skills), never the live one.
sandbox() {
  local home="$1"
  mkdir -p "$home/.agents/available-skills" "$home/.agents/bin" "$home/.claude/skills" "$home/.cursor/skills"
  ln -s "$CONFINER_SRC" "$home/.agents/bin/aubx-skills"
}

# Stand-in for the real CLI: writes exactly what `skills add -g` writes, into
# the HOME/AGENTS_HOME it is given (aubx-skills points both at a scratch tree).
make_installer() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
[ "${1:-}" = "skills" ] || { echo "stub: expected 'skills', got: $*" >&2; exit 1; }
name="${FAKE_SKILL:-demo-skill}"
agents_home="${AGENTS_HOME:?}"
mkdir -p "$agents_home/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$agents_home/skills/$name/SKILL.md"
printf '{"version":3,"skills":{"%s":{"source":"demo/repo","sourceType":"github"}}}\n' "$name" \
  >"$agents_home/.skill-lock.json"
for a in .claude .cursor; do
  mkdir -p "$HOME/$a/skills"
  ln -sfn "$agents_home/skills/$name" "$HOME/$a/skills/$name"
done
STUB
  chmod +x "$TMP/bin/aubx"
}
make_installer

# --- a global install lands only in the roster ------------------------------
home="$TMP/home"
sandbox "$home"
PATH="$TMP/bin:$PATH" HOME="$home" AGENTS_HOME="$home/.agents" "$SHIM" add demo/repo -g -y \
  >"$TMP/u.log" 2>&1
rc=$?

assert "shim exits 0" "[ $rc -eq 0 ]"
assert "skill lives in the roster" "[ -f '$home/.agents/available-skills/demo-skill/SKILL.md' ]"
assert "no record outside the roster" "[ ! -e '$home/.agents/.skill-lock.json' ]"
assert "record kept inside the roster" "grep -q demo-skill '$home/.agents/available-skills/.skill-lock.json'"
assert "no claude harness link" "[ ! -e '$home/.claude/skills/demo-skill' ]"
assert "no cursor harness link" "[ ! -e '$home/.cursor/skills/demo-skill' ]"
assert "nothing left in an auto-scan dir outside the roster" \
  "[ ! -e '$home/.agents/skills/demo-skill' ]"

# --- no confiner means refuse, not fall through to the unconfined CLI -------
# --- no confiner anywhere means refuse, not fall through to the unconfined CLI
# A shim with no sibling aubx-skills (copied out of ~/.local/bin) and an
# AGENTS_HOME with no bin/ either: there is nothing to confine with.
home2="$TMP/home2"
mkdir -p "$TMP/lonely" "$home2/.agents/available-skills"
cp "$SHIM" "$TMP/lonely/skills"
chmod +x "$TMP/lonely/skills"
PATH="$TMP/bin:$PATH" HOME="$home2" AGENTS_HOME="$home2/.agents" "$TMP/lonely/skills" add demo/repo -g -y \
  >"$TMP/r.log" 2>&1
rc2=$?
assert "missing confiner exits 127" "[ $rc2 -eq 127 ]"
assert "missing confiner installs nothing" "[ ! -e '$home2/.agents/available-skills/demo-skill' ]"
assert "missing confiner names the refusal" "grep -q 'refusing to write outside' '$TMP/r.log'"

# --- a project install is the user's call and passes through unconfined ----
home3="$TMP/home3"
sandbox "$home3"
mkdir -p "$TMP/cli"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/cli/skills"
chmod +x "$TMP/cli/skills"
PATH="$TMP/cli:$TMP/bin:$PATH" HOME="$home3" AGENTS_HOME="$home3/.agents" \
  "$SHIM" add demo/repo -p -y >"$TMP/p.log" 2>&1
assert "project add skips the confiner" "! grep -q 'confined to' '$TMP/p.log'"

if [ "$fail" -eq 0 ]; then echo "all skills-shim confinement checks passed"; else echo "FAILURES"; exit 1; fi
