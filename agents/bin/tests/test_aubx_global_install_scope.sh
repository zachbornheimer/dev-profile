#!/usr/bin/env bash
# test_aubx_global_install_scope — `aubx skills add -g` writes only inside
# $AGENTS_HOME/available-skills.
#
# Runs the real installer against a throwaway HOME that mirrors every harness
# skill root, then diffs the whole throwaway tree. Nothing outside
# <home>/.agents/available-skills may appear.
#
# --control runs the same install straight through the installer binary with no
# confiner. That arm must FAIL this assertion; it proves the test can see a leak
# instead of passing because the installer happened to write nothing.
set -uo pipefail

mode=confined
[ "${1:-}" = "--control" ] && mode=control

base="$(mktemp -d "${TMPDIR:-/tmp}/aubx-scope-test.XXXXXX")" || exit 1
trap 'rm -rf "$base"' EXIT
home="$base/home"
mkdir -p "$home/.claude/skills" "$home/.codex/skills" "$home/.grok/skills" \
         "$home/.cursor/skills" "$home/.config/opencode/skills" "$home/.agents/skills" \
         "$base/pkg/confine-proof"
printf -- '---\nname: confine-proof\ndescription: probe skill used to prove install scope\n---\n# confine proof\n' \
  >"$base/pkg/confine-proof/SKILL.md"

snap() { find "$home" -mindepth 1 2>/dev/null | sort; }
snap >"$base/before.txt"

if [ "$mode" = control ]; then
  # Resolve the installer itself, skipping the guard directory on PATH.
  real=""
  while IFS= read -r d; do
    [ "$(cd "$d" 2>/dev/null && pwd -P)" = "$(cd "$HOME/.agents/bin" && pwd -P)" ] && continue
    # ~/.local/bin/aubx is a symlink to the guard, so a directory-name skip
    # picks the confiner and the control stops leaking. Compare file identity,
    # the same way the guard does.
    [ -e "$d/aubx" ] && [ "$d/aubx" -ef "$HOME/.agents/bin/aubx" ] && continue
    if [ -x "$d/aubx" ]; then real="$d/aubx"; break; fi
  done < <(tr ':' '\n' <<<"$PATH")
  [ -n "$real" ] || real="$(ls "$HOME"/.local/share/mise/installs/aube/*/.mise-bins/aubx 2>/dev/null | head -1)"
  [ -n "$real" ] || { echo "SKIP control: no installer binary found"; exit 77; }
  env -u AUBX_SKILLS_CONFINED HOME="$home" AGENTS_HOME="$home/.agents" \
    timeout 240 "$real" skills add "$base/pkg/confine-proof" -g -y -a codex \
    >"$base/run.log" 2>&1
else
  env HOME="$home" AGENTS_HOME="$home/.agents" AUBX_AGENT=codex \
    timeout 240 aubx skills add "$base/pkg/confine-proof" -g -y \
    >"$base/run.log" 2>&1
fi
rc=$?
snap >"$base/after.txt"

new="$(comm -13 "$base/before.txt" "$base/after.txt")"
escaped=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$p" in
    "$home/.agents/available-skills"|"$home/.agents/available-skills"/*) ;;
    *) escaped="$escaped
  $p" ;;
  esac
done <<<"$new"

landed=0
[ -f "$home/.agents/available-skills/confine-proof/SKILL.md" ] && landed=1

if [ "$mode" = control ]; then
  # The unconfined arm is expected to leak; a clean run means the test cannot
  # tell a leak from a clean install and must not be trusted.
  if [ -z "$escaped" ]; then
    echo "FAIL control: unconfined install wrote nowhere outside available-skills; test has no discriminating power"
    tail -5 "$base/run.log"
    exit 1
  fi
  echo "PASS control: unconfined install leaked where the confined run must not:$escaped"
  exit 0
fi

if [ -n "$escaped" ]; then
  echo "FAIL: global install wrote outside available-skills:$escaped"
  tail -20 "$base/run.log"
  exit 1
fi
if [ "$landed" -ne 1 ]; then
  echo "FAIL: nothing landed in available-skills (installer rc=$rc); a clean diff must not pass as success"
  tail -20 "$base/run.log"
  exit 1
fi
echo "PASS: install landed only in available-skills"
