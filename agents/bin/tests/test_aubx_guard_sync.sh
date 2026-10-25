#!/usr/bin/env bash
# shellcheck disable=SC2034 # out and rc are read by assert's eval'd condition strings
# Proves the guard refuses the aubx verbs that write skill files straight into
# harness skill roots, so a global skill write can only land in available-skills.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
GUARD="$BIN/aubx"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$HOME/.claude/skills" "$HOME/.codex/skills" "$AGENTS_HOME/available-skills" "$TMP/bin"

# A real-aubx stand-in. The refused verbs must never reach it.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
echo "stub: reached with $*" >&2
exit 1
STUB
chmod +x "$TMP/bin/aubx"
PATH="$BIN:$TMP/bin:$PATH"

for verb in sync experimental_sync experimental_install; do
  out=""; rc=0
  out="$("$GUARD" skills "$verb" 2>&1)" || rc=$?
  assert "skills $verb exits 2" '[ "$rc" -eq 2 ]'
  assert "skills $verb names available-skills" 'case "$out" in *available-skills*) true ;; *) false ;; esac'
  assert "skills $verb never reached the installer" 'case "$out" in *stub:*) false ;; *) true ;; esac'
done

assert "no harness skill root gained entries" \
  '[ -z "$(ls -A "$HOME/.claude/skills")" ] && [ -z "$(ls -A "$HOME/.codex/skills")" ]'

# The confined path still passes through to the installer.
rc=0; out="$("$GUARD" skills add example/repo -g -y 2>&1)" || rc=$?
assert "skills add still reaches the installer" 'case "$out" in *stub:*) true ;; *) false ;; esac'

[ "$fail" -eq 0 ] && echo "PASS test_aubx_guard_sync.sh"
exit "$fail"
