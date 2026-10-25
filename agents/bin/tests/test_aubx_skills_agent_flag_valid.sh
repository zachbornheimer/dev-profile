#!/usr/bin/env bash
# Proves the agent flag aubx-skills hands the installer is one the CLI accepts.
#
# The sibling tests stub `aubx`, so they stay green whatever agent id the
# wrapper sends. A shim once shipped `-a cline,codex,dexto,fx,loaf,pi,warp,zed`
# — a single comma-joined token the CLI rejects outright ("Invalid agents"), so
# no install could succeed — and every stub-based test still passed. This test
# reads the agent out of a recorded invocation and asks the installed CLI
# whether it accepts that id.
#
# The CLI check is skipped, loudly, when no working aubx guard is reachable.
set -uo pipefail

BIN="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="$BIN/aubx-skills"
GUARD="$BIN/aubx"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

PATH_ORIG="$PATH"
mkdir -p "$TMP/home/.agents/available-skills" "$TMP/bin"
export HOME="$TMP/home" AGENTS_HOME="$TMP/home/.agents"

# Records the argv it is handed, then installs nothing.
cat >"$TMP/bin/aubx" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$STUB_ARGV"
STUB
chmod +x "$TMP/bin/aubx"

STUB_ARGV="$TMP/argv.txt" PATH="$TMP/bin:$PATH" "$WRAPPER" add example/repo --skill demo -y >"$TMP/run.log" 2>&1
rc=$?
assert "wrapper exit 0" "[ $rc -eq 0 ]"
assert "argv recorded" "[ -s '$TMP/argv.txt' ]"

# Pair each -a/--agent with the value that follows it.
agent=""
agent_count=0
prev=""
while IFS= read -r line; do
  case "$prev" in
    -a|--agent) agent="$line"; agent_count=$((agent_count + 1)) ;;
  esac
  prev="$line"
done <"$TMP/argv.txt"

assert "wrapper names exactly one agent" "[ $agent_count -eq 1 ]"
comma=0
case "$agent" in *,*) comma=1 ;; esac
assert "no comma-joined agent list" "[ $comma -eq 0 ]"
assert "agent id is not empty" "[ -n '$agent' ]"

# Ask the real CLI whether it accepts the id the wrapper sends.
if [ -x "$GUARD" ] && [ "$agent_count" -eq 1 ] && [ "$comma" -eq 0 ] && [ -n "$agent" ]; then
  if out=$(PATH="$PATH_ORIG" timeout 180 "$GUARD" skills ls -g -a "$agent" 2>&1); then
    echo "ok   - installed CLI accepts agent '$agent'"
  else
    printf 'FAIL - installed CLI rejects agent %s\n' "$agent"
    printf '%s\n' "$out" | head -3
    fail=1
  fi
else
  echo "skip - no usable aubx guard at $GUARD"
fi

[ "$fail" -eq 0 ] && echo "PASS: wrapper agent flag accepted by the CLI"
exit "$fail"
