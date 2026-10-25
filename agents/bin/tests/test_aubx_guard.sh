#!/usr/bin/env bash
# Proves the aubx scope guard: `skills add|update|upgrade` is routed through
# aubx-skills (confined to available-skills) whether or not -g is given, an
# explicit -p/--project install passes through, and everything else passes
# through to the real aubx untouched.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
GUARD="$BIN/aubx"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/skills/typesafe-ai" "$HOME/.claude/skills" "$TMP/real" "$TMP/guard"
touch "$AGENTS_HOME/skills/typesafe-ai/SKILL.md"
cp "$GUARD" "$TMP/guard/aubx"
chmod +x "$TMP/guard/aubx"

# Real aubx stand-in: records argv, mimics the installer's writes. It installs
# globally into the auto-scan dir and symlinks into the harness, exactly like
# `aubx skills add` does when it decides the scope itself.
cat >"$TMP/real/aubx" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$HOME/argv.log"
[ "$1" = "skills" ] || { echo "passthrough"; exit 0; }
name=""; prev=""
for a in "$@"; do [ "$prev" = "--skill" ] && name="$a"; prev="$a"; done
mkdir -p "$AGENTS_HOME/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$AGENTS_HOME/skills/$name/SKILL.md"
ln -sfn "$AGENTS_HOME/skills/$name" "$HOME/.claude/skills/$name"
STUB
chmod +x "$TMP/real/aubx"

# aubx-skills stand-in in the guard's own dir: records its argv and writes
# only into available-skills.
cat >"$TMP/guard/aubx-skills" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$HOME/confined.log"
name=""; prev=""
for a in "$@"; do [ "$prev" = "--skill" ] && name="$a"; prev="$a"; done
mkdir -p "$AGENTS_HOME/available-skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$AGENTS_HOME/available-skills/$name/SKILL.md"
STUB
chmod +x "$TMP/guard/aubx-skills"

run() { PATH="$TMP/guard:$TMP/real:$PATH" "$TMP/guard/aubx" "$@"; }

run skills add example/repo --skill demo -g -y >"$TMP/a.log" 2>&1
assert "global add routed to aubx-skills" "grep -q 'add example/repo --skill demo -g -y' \"\$HOME/confined.log\""
assert "global add did not hit real aubx" "[ ! -f \"\$HOME/argv.log\" ]"
assert "content only in available-skills" "[ -f \"\$AGENTS_HOME/available-skills/demo/SKILL.md\" ]"
assert "nothing in auto-scan dir" "[ ! -e \"\$AGENTS_HOME/skills/demo\" ]"
assert "no harness link" "[ ! -e \"\$HOME/.claude/skills/demo\" ]"

# The installer chooses global on its own when -y is given outside a project and
# no -g is passed. That path must be confined too, or a harness link leaks.
run skills add example/repo --skill demo2 -y >"$TMP/f.log" 2>&1
assert "add without -g is confined" "grep -q 'add example/repo --skill demo2 -y' \"\$HOME/confined.log\""
assert "add without -g did not hit real aubx" "! grep -q 'demo2' \"\$HOME/argv.log\""
assert "add without -g left no harness link" "[ ! -e \"\$HOME/.claude/skills/demo2\" ]"
assert "add without -g left nothing in auto-scan dir" "[ ! -e \"\$AGENTS_HOME/skills/demo2\" ]"

run skills update -y >"$TMP/g.log" 2>&1
assert "update without -g is confined" "grep -q 'update -y' \"\$HOME/confined.log\""
assert "update without -g did not hit real aubx" "! grep -q '^skills update -y' \"\$HOME/argv.log\""

# Removing a skill deletes a roster folder, the harness links to it, and its
# record entry: the same three writes an install makes, so it takes the same
# confined path. Left to pass through it deleted harness links and rewrote
# ~/.agents/.skill-lock.json, both outside available-skills.
run skills remove demo9 -g -y >"$TMP/h1.log" 2>&1
assert "global remove routed to aubx-skills" "grep -q 'remove demo9 -g -y' \"\$HOME/confined.log\""
assert "global remove did not hit real aubx" "! grep -q 'skills remove demo9' \"\$HOME/argv.log\""

run skills rm demo9 -g >"$TMP/h2.log" 2>&1
assert "rm alias is confined" "grep -q 'rm demo9 -g' \"\$HOME/confined.log\""

run skills remove demo9 -y >"$TMP/h3.log" 2>&1
assert "remove without -g is confined" "grep -q 'remove demo9 -y' \"\$HOME/confined.log\""

run skills remove demo9 -p >"$TMP/h4.log" 2>&1
assert "explicit -p project remove passes through" "grep -q 'skills remove demo9 -p' \"\$HOME/argv.log\""

run skills add example/repo --skill local -p >"$TMP/b.log" 2>&1
assert "explicit -p project add passes through" "grep -q 'skills add example/repo --skill local -p' \"\$HOME/argv.log\""

run cowsay hello >"$TMP/c.log" 2>&1
assert "non-skills command passes through" "grep -qx 'cowsay hello' \"\$HOME/argv.log\""

run skills list >"$TMP/d.log" 2>&1
assert "skills list passes through" "grep -qx 'skills list' \"\$HOME/argv.log\""

run --help >"$TMP/e.log" 2>&1
assert "bare help passes through" "grep -qx -- '--help' \"\$HOME/argv.log\""

# `--help` on a subcommand must reach the real aubx. Routed into the confiner it
# errored out demanding a package source, so `skills add --help` printed an
# error instead of the flags the user was trying to read.
run skills add example/repo --skill demohelp --help >"$TMP/i.log" 2>&1
assert "subcommand add --help passes through" "grep -qx 'skills add example/repo --skill demohelp --help' \"\$HOME/argv.log\""
assert "subcommand add --help did not reach the confiner" "! grep -q 'demohelp' \"\$HOME/confined.log\""

run skills sync --help >"$TMP/j.log" 2>&1
assert "help on a refused verb still reaches real aubx" "grep -qx 'skills sync --help' \"\$HOME/argv.log\""

exit "$fail"
