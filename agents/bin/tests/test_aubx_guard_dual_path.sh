#!/usr/bin/env bash
# Proves the guard still routes a global install when the same shim file is
# reachable at two PATH locations — ~/.agents/bin/aubx plus a symlink to it from
# a harness bin dir (~/.local/bin/aubx). Resolving "the real aubx" by directory
# only finds the second path, execs it, and the guard re-enters itself until the
# OS kills the run. The guard must skip any candidate that resolves to itself.
set -uo pipefail

REAL_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$TMP/agents/bin" "$TMP/local/bin" "$TMP/real"
cp "$REAL_DIR/aubx" "$TMP/agents/bin/aubx"
chmod +x "$TMP/agents/bin/aubx"
ln -s "$TMP/agents/bin/aubx" "$TMP/local/bin/aubx"

# Confiner stand-in beside the guard: records argv, writes only the roster.
cat >"$TMP/agents/bin/aubx-skills" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$TMP/confined.log"
STUB
chmod +x "$TMP/agents/bin/aubx-skills"

# The real installer stand-in must not be reached: reaching it means the guard
# passed the write through unconfined.
cat >"$TMP/real/aubx" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$TMP/real.log"
STUB
chmod +x "$TMP/real/aubx"

fail=0
assert() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

run_case() { # name, PATH order
  local name="$1" path="$2" rc
  rm -f "$TMP/confined.log" "$TMP/real.log"
  PATH="$path:$PATH" timeout 15 "$TMP/agents/bin/aubx" skills add example/repo --skill a1 -g -y \
    >"$TMP/$name.log" 2>&1
  rc=$?
  assert "$name: exits 0 (no recursion/timeout)" "[ $rc -eq 0 ]"
  assert "$name: routed to confiner"            "grep -q 'skills add example/repo --skill a1 -g -y' '$TMP/confined.log' 2>/dev/null"
  assert "$name: installer never reached"       "[ ! -f '$TMP/real.log' ]"
  assert "$name: no re-entry error"             "! grep -q 're-entered itself' '$TMP/$name.log'"
}

run_case guard_dir_first "$TMP/agents/bin:$TMP/local/bin:$TMP/real"
run_case symlink_first   "$TMP/local/bin:$TMP/agents/bin:$TMP/real"

exit "$fail"
