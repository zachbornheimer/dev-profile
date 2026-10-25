#!/usr/bin/env bash
# shellcheck disable=SC2034 # out and rc are read by assert's eval'd condition strings
# Proves `dlx skills` cannot smuggle a global skill install past the scope guard.
#
# `aubx skills add` and `aube skills add` are confined by their shims, but
# `aubx dlx skills add` / `aube dlx skills add` reach the same installer one
# level deeper and used to pass straight through, writing ~/.agents/skills,
# ~/.agents/.skill-lock.json and a link in every detected harness. Both shims
# now normalize the dlx form onto the confined path.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$TMP/bin"

# Stand-in for the real installer: writes wherever $HOME points, like the real one.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
# On this machine `aubx` is aube, so a real aubx forwards dlx to aube.
[ "$1" = "dlx" ] && { command aube "$@"; exit $?; }
[ "$1" = "skills" ] && [ "$2" = "add" ] || { echo "stub-aubx: bad invocation: $*" >&2; exit 1; }
case " $* " in *" -g "*|*" --global "*) ;; *) echo "stub-aubx: global flag missing" >&2; exit 1 ;; esac
name=""; prev=""
for a in "$@"; do
  [ "$prev" = "--skill" ] && name="$a"
  prev="$a"
done
[ -n "$name" ] || { echo "stub-aubx: no --skill given" >&2; exit 1; }
mkdir -p "$HOME/.agents/skills/$name"
printf -- '---\nname: %s\n---\n' "$name" >"$HOME/.agents/skills/$name/SKILL.md"
printf -- '{"version":3,"skills":{"%s":{"source":"example/repo"}}}\n' "$name" >"$HOME/.agents/.skill-lock.json"
ln -sfn "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name"
STUB
chmod +x "$TMP/bin/aubx"

# Stand-in for the real aube: any arrival here means a pass-through leak.
cat >"$TMP/bin/aube" <<'STUB'
#!/usr/bin/env bash
echo "stub-aube: reached with $*" >&2
exit 1
STUB
chmod +x "$TMP/bin/aube"

PATH="$BIN:$TMP/bin:$PATH"
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

for shim in aubx aube; do
  rm -rf "$HOME/.agents/skills" "$HOME/.agents/.skill-lock.json" \
         "$AGENTS_HOME/available-skills/demo-skill" "$HOME/.claude/skills/demo-skill"
  rc=0
  out="$("$BIN/$shim" dlx skills add example/repo --skill demo-skill -g -y 2>&1)" || rc=$?
  assert "$shim dlx skills add exits 0" '[ "$rc" -eq 0 ]'
  assert "$shim dlx never reached the raw aube" 'case "$out" in *stub-aube:*) false ;; *) true ;; esac'
  assert "$shim dlx landed in available-skills" "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
  assert "$shim dlx left no ~/.agents/skills copy" "[ ! -e \"$HOME/.agents/skills/demo-skill\" ]"
  assert "$shim dlx left no ~/.agents/.skill-lock.json" "[ ! -e \"$HOME/.agents/.skill-lock.json\" ]"
  assert "$shim dlx left no harness link" "[ ! -e \"$HOME/.claude/skills/demo-skill\" ] && [ ! -L \"$HOME/.claude/skills/demo-skill\" ]"
  assert "$shim dlx claims clean scope" 'case "$out" in *"no writes outside"*) true ;; *) false ;; esac'
done

# Non-skills dlx still passes through untouched.
out="$("$BIN/aube" dlx cowsay hello 2>&1)"
assert "aube dlx <other> still passes through" 'case "$out" in *stub-aube:*) true ;; *) false ;; esac'
out="$("$BIN/aubx" dlx cowsay hello 2>&1)"
assert "aubx dlx <other> still passes through" 'case "$out" in *stub-aube:*) true ;; *) false ;; esac'

# A dlx skills write verb the confiner refuses must still be refused.
for verb in sync experimental_sync experimental_install; do
  rc=0
  out="$("$BIN/aube" dlx skills "$verb" 2>&1)" || rc=$?
  assert "aube dlx skills $verb exits 2" '[ "$rc" -eq 2 ]'
  assert "aube dlx skills $verb never reached the installer" 'case "$out" in *stub-aubx:*) false ;; *) true ;; esac'
done

[ "$fail" -eq 0 ] && echo "PASS test_aubx_guard_dlx.sh"
exit "$fail"
