#!/usr/bin/env bash
# Proves the strict contract: aubx-skills runs the installer under a throwaway
# HOME so its writes land in scratch, copies the result into available-skills,
# and fails loudly (exit 3) when the installer reaches a real path anyway.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$BIN/aubx-skills"
GUARD="$BIN/aubx"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

REAL_HOME="$TMP/home"

# $1 = shell snippet the installer runs AFTER its normal install; it models an
# installer that ignores $HOME and writes straight to a real machine path.
make_stub() {
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/aubx" <<STUB
#!/usr/bin/env bash
[ "\$1" = "skills" ] || { echo "stub: bad invocation: \$*" >&2; exit 1; }
case " \$* " in *" -g "*) ;; *) echo "stub: global flag missing" >&2; exit 1 ;; esac
name=""; prev=""
for a in "\$@"; do [ "\$prev" = "--skill" ] && name="\$a"; prev="\$a"; done
if [ "\$2" = "update" ]; then
  # An update rewrites what the seeded record lists.
  name="\$(basename "\$(ls -d "\$AGENTS_HOME"/skills/*/ | head -1)")"
  [ -n "\$name" ] || { echo "stub: update found nothing seeded" >&2; exit 1; }
  printf -- '---\nname: %s\nupdated: true\n---\n' "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
  printf '{"version":3,"skills":{"%s":{"source":"example/repo"}}}\n' "\$name" >"\$AGENTS_HOME/.skill-lock.json"
  $1
  exit 0
fi
[ -n "\$name" ] || { echo "stub: no --skill given" >&2; exit 1; }
mkdir -p "\$AGENTS_HOME/skills/\$name"
printf -- '---\nname: %s\ndescription: fixture\n---\n' "\$name" >"\$AGENTS_HOME/skills/\$name/SKILL.md"
mkdir -p "\$HOME/.claude/skills"
ln -sfn "\$AGENTS_HOME/skills/\$name" "\$HOME/.claude/skills/\$name"
$1
STUB
  chmod +x "$TMP/bin/aubx"
}

setup_home() {
  rm -rf "${TMP:?}/home"; mkdir -p "$TMP/home/.agents" "$TMP/home/.claude/skills" "$TMP/home/.codex/skills"
  export HOME="$TMP/home" AGENTS_HOME="$TMP/home/.agents"
}

# Case A: installer installs under the scratch HOME; the skill must reach the
# available-skills tree, and no harness link may survive anywhere.
setup_home
make_stub ':'
PATH="$TMP/bin:$PATH" "$WRAPPER" skills add example/repo --skill demo -g -y >"$TMP/a.log" 2>&1
rc=$?
assert "case A exit 0"               "[ $rc -eq 0 ]"
assert "pins -a codex"               "grep -q 'a codex' '$TMP/a.log'"
assert "no harness link left"        "[ ! -e \"$REAL_HOME/.claude/skills/demo\" ] && [ ! -L \"$REAL_HOME/.claude/skills/demo\" ]"
assert "nothing in auto-scan dir"    "[ ! -e \"$REAL_HOME/.agents/skills/demo\" ]"
assert "content in available-skills" "[ -f \"$REAL_HOME/.agents/available-skills/demo/SKILL.md\" ]"
# A clean install must also keep stderr clean: the audit reads ${#violations[@]},
# which bash 3.2 reports as an unbound variable under set -u when the array was
# never declared. That aborts the check while the run still prints success.
assert "case A stderr carries no unbound-variable noise" "! grep -q 'unbound variable' '$TMP/a.log'"

# Case B: installer ignores $HOME and writes a real dir outside
# available-skills -> exit 3 and the path is named.
setup_home
make_stub "mkdir -p '$REAL_HOME/.codex/skills/rogue'; echo x >'$REAL_HOME/.codex/skills/rogue/SKILL.md'"
PATH="$TMP/bin:$PATH" "$WRAPPER" skills add example/repo --skill demo -g -y >"$TMP/b.log" 2>&1
rc=$?
assert "case B exit 3"              "[ $rc -eq 3 ]"
assert "case B names the violation" "grep -q 'WROTE OUTSIDE' '$TMP/b.log' && grep -q 'rogue' '$TMP/b.log'"

# Case C: the guard delegates a global update to the confining wrapper, so an
# update rewrites the skill inside available-skills and writes nothing else.
setup_home
mkdir -p "$REAL_HOME/.agents/available-skills/demo"
printf -- '---\nname: demo\ndescription: fixture\n---\n' >"$REAL_HOME/.agents/available-skills/demo/SKILL.md"
printf '{"version":3,"skills":{"demo":{"source":"example/repo"}}}\n' >"$REAL_HOME/.agents/available-skills/.skill-lock.json"
make_stub ':'
PATH="$BIN:$TMP/bin:$PATH" "$GUARD" skills update -g -y >"$TMP/c.log" 2>&1
rc=$?
assert "update exit 0"                            "[ $rc -eq 0 ]"
assert "update left no ~/.agents lock"            "[ ! -e \"$REAL_HOME/.agents/.skill-lock.json\" ]"
assert "update rewrote the skill in place"        "grep -q 'updated: true' '$REAL_HOME/.agents/available-skills/demo/SKILL.md'"
assert "update record kept inside available-skills" "[ -f \"$REAL_HOME/.agents/available-skills/.skill-lock.json\" ]"

# Case D: a harness root that is a symlink into available-skills is not a leak.
# The record the wrapper merges into available-skills/.skill-lock.json also shows
# up under ~/.grok/skills, because that root is the same directory. The audit must
# compare resolved paths, not literal strings, or every real install exits 3.
setup_home
mkdir -p "$REAL_HOME/.agents/available-skills" "$REAL_HOME/.grok"
ln -sfn "$REAL_HOME/.agents/available-skills" "$REAL_HOME/.grok/skills"
make_stub 'mkdir -p "$AGENTS_HOME"; printf "%s\n" "{\"version\":3,\"skills\":{\"demo\":{\"source\":\"example/repo\"}}}" >"$AGENTS_HOME/.skill-lock.json"'
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo -y >"$TMP/d.log" 2>&1
rc=$?
assert "case D exit 0 (harness root symlinked to available-skills)" "[ $rc -eq 0 ]"
assert "case D kept the record in available-skills"                 "[ -f \"$REAL_HOME/.agents/available-skills/.skill-lock.json\" ]"
assert "case D reported no violation"                               "! grep -q 'WROTE OUTSIDE' '$TMP/d.log'"
# Case E: a stray link whose target is spelled through ~/.agents/skills — itself a
# symlink to available-skills — is harmless. The audit must resolve the target,
# remove the link, and report no violation; matching the raw string flagged a
# clean install as a leak.
setup_home
mkdir -p "$REAL_HOME/.agents/available-skills"
rm -rf "$REAL_HOME/.agents/skills"
ln -sfn "$REAL_HOME/.agents/available-skills" "$REAL_HOME/.agents/skills"
make_stub 'mkdir -p "'"$REAL_HOME"'/.claude/skills"; ln -sfn "../../.agents/skills/demo" "'"$REAL_HOME"'/.claude/skills/demo"'
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo -g -y >"$TMP/e.log" 2>&1
rc=$?
assert "case E exit 0 (stray link spelled via .agents/skills)" "[ $rc -eq 0 ]"
assert "case E removed the stray link"                         "[ ! -L \"$REAL_HOME/.claude/skills/demo\" ]"
assert "case E reported no violation"                          "! grep -q 'WROTE OUTSIDE' '$TMP/e.log'"

# Case F: a record an older installer left at ~/.agents/.skill-lock.json is
# folded into the roster record and removed, so a repair leaves no second
# skill-state file outside available-skills. An entry with no backing folder is
# a ghost, and the roster must not gain it. The roster copy wins a conflict: it
# is the canonical record, and a stale stray must not overwrite it. (Case F2
# covers an entry that IS backed by a real folder.)
setup_home
mkdir -p "$REAL_HOME/.agents/available-skills"
printf '{"version":3,"skills":{"demo":{"source":"example/roster"}}}\n' >"$REAL_HOME/.agents/available-skills/.skill-lock.json"
printf '{"version":3,"skills":{"ghost":{"source":"example/ghost"},"demo":{"source":"example/stale"}}}\n' >"$REAL_HOME/.agents/.skill-lock.json"
make_stub ':'
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo -g -y >"$TMP/f.log" 2>&1
rc=$?
record="$REAL_HOME/.agents/available-skills/.skill-lock.json"
assert "case F exit 0 (stray record self-heals)"   "[ $rc -eq 0 ]"
assert "case F removed the stray record"           "[ ! -e \"$REAL_HOME/.agents/.skill-lock.json\" ]"
assert "case F dropped the entry with no backing folder" "! jq -e '.skills.ghost' \"$record\" >/dev/null 2>&1"
assert "case F roster entry wins the conflict"     "[ \"\$(jq -r '.skills.demo.source' \"$record\")\" = example/roster ]"
assert "case F reported no violation"              "! grep -q 'WROTE OUTSIDE' '$TMP/f.log'"

# Case F2: a stray entry that IS backed by a skill folder in the roster is real
# state, not a phantom, so folding the stray record in must carry it over.
setup_home
mkdir -p "$REAL_HOME/.agents/available-skills/extra"
printf -- '---\nname: extra\ndescription: fixture\n---\n' >"$REAL_HOME/.agents/available-skills/extra/SKILL.md"
printf '{"version":3,"skills":{}}\n' >"$REAL_HOME/.agents/available-skills/.skill-lock.json"
printf '{"version":3,"skills":{"extra":{"source":"example/extra"}}}\n' >"$REAL_HOME/.agents/.skill-lock.json"
make_stub ':'
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo -g -y >"$TMP/f2.log" 2>&1
rc=$?
record="$REAL_HOME/.agents/available-skills/.skill-lock.json"
assert "case F2 exit 0"                         "[ $rc -eq 0 ]"
assert "case F2 merged the folder-backed entry" "jq -e '.skills.extra' \"$record\" >/dev/null 2>&1"
assert "case F2 reported no violation"          "! grep -q 'WROTE OUTSIDE' '$TMP/f2.log'"

# Case C: another tool writing inside AGENTS_HOME (an AGENTS.md edit leaves a
# .orig beside it) is not the skills installer doing it and must not be
# reported as a leak, or every correctly confined install fails.
setup_home
make_stub 'mkdir -p "$HOME/.agents"; printf "x\n" >"$HOME/.agents/AGENTS.md.orig"'
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo -y >"$TMP/c.log" 2>&1
rc=$?
assert "case C exit 0"                    "[ $rc -eq 0 ]"
assert "case C reports no violation"      "! grep -q 'WROTE OUTSIDE' '$TMP/c.log'"
assert "case C still installed the skill" "[ -f \"\$AGENTS_HOME/available-skills/demo/SKILL.md\" ]"

# Case C2: a fresh install record written straight into the real AGENTS_HOME is
# self-healed, not left behind and not a violation. The record is the
# installer's own bookkeeping, so it is merged into
# available-skills/.skill-lock.json and the stray is removed; only a real file
# or dir other than that record is a leak. (Case F covers the conflict merge.)
setup_home
make_stub "printf '{\"version\":3,\"skills\":{\"demo\":{\"source\":\"example/repo\"}}}\n' >\"$REAL_HOME/.agents/.skill-lock.json\""
PATH="$TMP/bin:$PATH" "$WRAPPER" example/repo --skill demo -y >"$TMP/c2.log" 2>&1
rc=$?
assert "case C2 exit 0 (fresh stray record self-heals)" "[ $rc -eq 0 ]"
assert "case C2 removed the stray record"               "[ ! -e \"$REAL_HOME/.agents/.skill-lock.json\" ]"
assert "case C2 merged it into available-skills"        "jq -e '.skills.demo' \"$REAL_HOME/.agents/available-skills/.skill-lock.json\" >/dev/null 2>&1"
assert "case C2 reported no violation"                  "! grep -q 'WROTE OUTSIDE' '$TMP/c2.log'"
exit "$fail"
