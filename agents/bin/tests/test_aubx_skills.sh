#!/usr/bin/env bash
# Proves aubx-skills writes ONLY inside $AGENTS_HOME/available-skills:
#   1. install relocates out of the sandbox scan dir, no harness links survive,
#   2. reinstall replaces the roster copy (no stale duplicate),
#   3. lock entries merge into available-skills/.skill-lock.json,
#   4. remove deletes the roster copy and its lock entry,
#   5. a legacy scan-dir copy of the same name is left untouched and still gets
#      no harness link (on this machine ~/.agents/skills is a symlink to
#      available-skills, so the scan dir and the roster are one path),
#   6. the sandbox is always cleaned up.
set -uo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
export TMPDIR="$TMP/tmp"
mkdir -p "$AGENTS_HOME/skills/typesafe-ai" "$HOME/.claude/skills" "$TMP/bin" "$TMPDIR"
touch "$AGENTS_HOME/skills/typesafe-ai/SKILL.md"

# Stand-in for the real aubx: mimics everything the real installer scatters.
# Both verbs are modelled because the confiner delegates remove to the same
# installer it delegates add to, and the two take names differently: add reads
# them from --skill, remove takes them positionally.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
[ "${1:-}" = "skills" ] || { echo "stub aubx: only skills supported" >&2; exit 1; }
verb="${2:-}"
shift 2 || shift $#
names=()
case "$verb" in
add)
  prev=""
  for a in "$@"; do
    [ "$prev" = "--skill" ] && names+=("$a")
    prev="$a"
  done
  ;;
remove | rm)
  skip=0
  for a in "$@"; do
    if [ "$skip" = 1 ]; then skip=0; continue; fi
    case "$a" in
    -a | --agent | -s | --skill | --subagent | --metadata) skip=1 ;;
    -*) ;;
    *) names+=("$a") ;;
    esac
  done
  ;;
*)
  echo "stub aubx: unsupported verb $verb" >&2
  exit 1
  ;;
esac
drop_record() {
  command -v jq >/dev/null 2>&1 || return 0
  [ -f "$HOME/.agents/.skill-lock.json" ] || return 0
  jq --arg n "$1" 'del(.skills[$n])' "$HOME/.agents/.skill-lock.json" >"$HOME/.agents/.skill-lock.json.t" &&
    mv "$HOME/.agents/.skill-lock.json.t" "$HOME/.agents/.skill-lock.json"
}
case "$verb" in
add)
  [ "${#names[@]}" -gt 0 ] || { echo "stub: no --skill" >&2; exit 1; }
  for name in "${names[@]}"; do
    mkdir -p "$HOME/.agents/skills/$name"
    printf -- '---\nname: %s\nrevision: %s\n---\n' "$name" "${STUB_REVISION:-1}" >"$HOME/.agents/skills/$name/SKILL.md"
    mkdir -p "$HOME/.claude/skills" "$HOME/.config/crush/skills" "$HOME/.codex/skills"
    ln -sfn "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name"
    ln -sfn "$HOME/.agents/skills/$name" "$HOME/.config/crush/skills/$name"
    printf '{"version":3,"skills":{"%s":{"source":"acme/repo","sourceType":"github","skillPath":"skills/%s/SKILL.md"}}}\n' "$name" "$name" >"$HOME/.agents/.skill-lock.json"
  done
  ;;
remove | rm)
  [ "${#names[@]}" -gt 0 ] || { echo "stub: no names" >&2; exit 2; }
  for name in "${names[@]}"; do
    [ -e "$HOME/.agents/skills/$name" ] || { echo "stub: not installed: $name" >&2; continue; }
    rm -rf "${HOME:?}/.agents/skills/$name"
    rm -f "$HOME/.claude/skills/$name" "$HOME/.config/crush/skills/$name"
    drop_record "$name"
  done
  ;;
esac
STUB
chmod +x "$TMP/bin/aubx"
script_dir="$(dirname "$WRAPPER")"
export PATH="$TMP/bin:$script_dir:/usr/bin:/bin:/usr/sbin:/sbin"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

"$WRAPPER" add acme/repo --skill demo-skill >/dev/null || fail=1
assert "installed into available-skills"      "[ -f \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\" ]"
assert "nothing left in auto-scan dir"        "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ]"
assert "no claude link created"               "[ ! -L \"$HOME/.claude/skills/demo-skill\" ]"
assert "no crush link created"                "[ ! -L \"$HOME/.config/crush/skills/demo-skill\" ]"
assert "no codex dir created"                 "[ ! -e \"$HOME/.codex\" ]"
assert "lock written inside available-skills" "grep -q demo-skill \"$AGENTS_HOME/available-skills/.skill-lock.json\""
assert "root lock not written"                "[ ! -e \"$AGENTS_HOME/.skill-lock.json\" ]"
assert "sandbox cleaned up"                   "[ -z \"\$(ls -A \"\$TMPDIR\" 2>/dev/null | grep '^aubx-skills\\.')\" ]"

STUB_REVISION=2 "$WRAPPER" add acme/repo --skill demo-skill >/dev/null || fail=1
assert "reinstall replaces roster copy"       "grep -q 'revision: 2' \"$AGENTS_HOME/available-skills/demo-skill/SKILL.md\""
assert "reinstall leaves scan dir clear"      "[ ! -e \"$AGENTS_HOME/skills/demo-skill\" ]"

"$WRAPPER" add acme/repo --skill other-skill >/dev/null || fail=1
# shellcheck disable=SC2034 # read by the eval'd assert condition below
out="$("$WRAPPER" list)"
assert "list reports roster"                  "printf '%s' \"\$out\" | grep -qx demo-skill && printf '%s' \"\$out\" | grep -qx other-skill"
assert "list excludes auto-scan skills"       "! printf '%s' \"\$out\" | grep -qx typesafe-ai"

"$WRAPPER" remove demo-skill >/dev/null || fail=1
assert "remove deletes roster copy"           "[ ! -e \"$AGENTS_HOME/available-skills/demo-skill\" ]"
assert "remove drops lock entry"              "! grep -q demo-skill \"$AGENTS_HOME/available-skills/.skill-lock.json\""
assert "remove keeps other skills"            "[ -f \"$AGENTS_HOME/available-skills/other-skill/SKILL.md\" ]"

# A copy already sitting in the legacy scan dir is not a refusal case any more.
# Installing that name must still write only the roster copy and leave no
# harness link behind.
status=0; "$WRAPPER" add acme/repo --skill typesafe-ai >/dev/null 2>&1 || status=$?
assert "install beside legacy scan-dir name succeeds" "[ $status -eq 0 ]"
assert "roster copy written"                  "[ -f \"$AGENTS_HOME/available-skills/typesafe-ai/SKILL.md\" ]"
assert "legacy scan-dir copy untouched"       "[ -f \"$AGENTS_HOME/skills/typesafe-ai/SKILL.md\" ] && [ ! -L \"$AGENTS_HOME/skills/typesafe-ai\" ]"
assert "no harness link for legacy name"      "[ ! -L \"$HOME/.claude/skills/typesafe-ai\" ]"

status=0; "$WRAPPER" experimental_sync >/dev/null 2>&1 || status=$?
assert "unknown subcommand rejected"          "[ $status -ne 0 ]"

exit "$fail"
