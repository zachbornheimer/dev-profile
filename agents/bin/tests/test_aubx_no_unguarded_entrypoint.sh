#!/usr/bin/env bash
# Proves no unguarded `aubx` / `aube` / `skills` is reachable by name.
#
# The guards only confine what reaches them. A raw installer sitting earlier on
# PATH — Homebrew's `aube` and `skills` kegs did exactly this — runs the real
# installer with a real $HOME and writes ~/.agents/skills, a link per harness,
# and ~/.agents/.skill-lock.json: the leak the guards exist to stop.
#
# So: in every directory a shell might resolve these names from, the first match
# must be a guard. A directory with no match is fine (the lookup fails closed).
set -uo pipefail

AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"
BIN="$AGENTS_HOME/bin"
GUARDS="$(cd "$BIN" && pwd -P)/aubx $(cd "$BIN" && pwd -P)/aube"
SKILLS_SHIM="$HOME/.local/bin/skills"
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

is_guard() {
  local path="$1" real
  [ -n "$path" ] || return 1
  [ -e "$path" ] || return 1
  real="$(cd "$(dirname "$path")" && pwd -P)/$(basename "$path")"
  real="$(readlink -f "$path" 2>/dev/null || printf '%s' "$real")"
  for g in $GUARDS; do [ "$real" = "$g" ] && return 0; done
  [ "$real" = "$SKILLS_SHIM" ] && return 0
  return 1
}

# 1. Entry directories that sit early on a PATH: anything named aubx/aube/skills
#    here must be a guard, because a shell resolves it by name.
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$BIN"; do
  [ -d "$d" ] || continue
  for name in aubx aube skills; do
    target="$d/$name"
    [ -e "$target" ] || continue
    if is_guard "$target"; then
      echo "ok   - $target is a guard"
    else
      echo "FAIL - $target is an unguarded $name"
      fail=1
    fi
  done
done

# 2. PATH shapes a tool may hand a child process. Resolving to nothing is fine;
#    resolving to a raw installer is the leak.
shapes=(
  "/opt/homebrew/bin:/usr/bin:/bin"
  "/usr/local/bin:/usr/bin:/bin"
  "$HOME/.local/bin:/usr/bin:/bin"
  "$BIN:/usr/bin:/bin"
  "/usr/bin:/bin"
)
for shape in "${shapes[@]}"; do
  for name in aubx aube skills; do
    found="$(PATH="$shape" command -v "$name" 2>/dev/null || true)"
    if [ -z "$found" ]; then
      echo "ok   - $name unresolved under $shape (fails closed)"
    elif is_guard "$found"; then
      echo "ok   - $name -> guard under $shape"
    else
      echo "FAIL - $name -> unguarded $found under $shape"
      fail=1
    fi
  done
done

# 3. The live roster stays the only durable skill state on the machine.
[ -L "$AGENTS_HOME/skills" ] \
  && echo "ok   - $AGENTS_HOME/skills is a link" \
  || { echo "FAIL - $AGENTS_HOME/skills is a real directory"; fail=1; }
[ ! -e "$AGENTS_HOME/.skill-lock.json" ] \
  && echo "ok   - no install record outside the roster" \
  || { echo "FAIL - $AGENTS_HOME/.skill-lock.json exists"; fail=1; }

if [ "$fail" -ne 0 ]; then
  echo "FAILED: an unguarded aubx/aube/skills entrypoint is reachable, or skill state sits outside $AGENTS_HOME/available-skills"
  exit 1
fi
echo "ok - every reachable aubx/aube/skills entrypoint is a guard"
