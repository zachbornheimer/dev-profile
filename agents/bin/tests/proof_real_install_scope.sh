#!/usr/bin/env bash
# Proof that a real global `aubx skills` install and remove touch nothing
# outside $AGENTS_HOME/available-skills.
#
# Installs a throwaway local probe skill, then removes it, snapshotting every
# root aubx's installer can reach before, between, and after. A local source
# keeps the check off the network: an earlier version ran
# `aubx skills update -g`, which re-resolves every recorded source with a git
# clone and was killed by the run deadline, so it never reached an assertion.
set -uo pipefail
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"
AVAILABLE="$AGENTS_HOME/available-skills"
probe="aubx-scope-probe-$$"
src="$(mktemp -d)"; b="$(mktemp)"; a="$(mktemp)"; c="$(mktemp)"
mkdir -p "$src/$probe"
printf -- '---\nname: %s\ndescription: temporary probe skill used to prove aubx write confinement; safe to delete\n---\n\nProbe.\n' \
  "$probe" >"$src/$probe/SKILL.md"
roots=("$AGENTS_HOME" "$HOME/.claude/skills" "$HOME/.codex/skills"
       "$HOME/.cursor/skills" "$HOME/.grok/skills" "$HOME/.gemini/skills"
       "$HOME/.config/opencode/skills")
snap() {
  local r
  for r in "${roots[@]}"; do
    [ -d "$r" ] || continue
    fd --min-depth 1 --max-depth 2 --hidden --no-ignore --absolute-path . "$r" \
      | grep -v "^$AGENTS_HOME/bin.tmp"
  done | sort
}
cleanup() { aubx skills remove -g "$probe" -y >/dev/null 2>&1; rm -rf "$src" "$b" "$a" "$c"; }
trap cleanup EXIT

fail=0
snap >"$b"
aubx skills add "$src" --skill "$probe" -g -y >/dev/null || { echo "installer failed"; exit 1; }
snap >"$a"
[ -d "$AVAILABLE/$probe" ] || { echo "install did not land in $AVAILABLE"; fail=1; }
leak="$(comm -13 "$b" "$a" | grep -v "^$AVAILABLE/" || true)"
if [ -n "$leak" ]; then printf 'WROTE OUTSIDE %s (install):\n%s\n' "$AVAILABLE" "$leak"; fail=1; fi

aubx skills remove -g "$probe" -y >/dev/null || { echo "remover failed"; exit 1; }
snap >"$c"
# Same scope rule as the install check above: writes inside AVAILABLE are
# permitted — parallel workers' selftests land there routinely — while anything
# new outside it after remove is a leak. The probe folder itself is checked
# explicitly below, so a remove that failed to delete it still fails here.
residue="$(comm -13 "$b" "$c" | grep -v "^$AVAILABLE/" || true)"
if [ -n "$residue" ]; then printf 'LEFT BEHIND AFTER REMOVE:\n%s\n' "$residue"; fail=1; fi
[ -e "$AVAILABLE/$probe" ] && { echo "probe folder survived remove"; fail=1; }

[ "$fail" -eq 0 ] && echo "ok - install and remove touched nothing outside $AVAILABLE"
exit "$fail"
