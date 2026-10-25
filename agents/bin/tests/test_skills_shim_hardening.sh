#!/usr/bin/env bash
# Proves the `skills` shim answers help and version without a network resolve,
# refuses the verbs that cannot be confined to the roster, cannot resolve itself
# as the real CLI, and bounds every child process.
#
# Each case runs against a sandboxed HOME/AGENTS_HOME with stub `aubx`,
# `aubx-skills` and `skills` executables, so nothing here can reach the live
# machine's confiner, the live roster, or the network. That matters most for the
# refusal cases: the point is that the write never happens, and a stub proves it
# the way a real `sync` run could not.
set -uo pipefail

SHIM="${SHIM:-$HOME/.local/bin/skills}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
assert() {
	if eval "$2"; then echo "ok   - $1"; else
		echo "FAIL - $1"
		fail=1
	fi
}

[ -x "$SHIM" ] || {
	echo "FAIL - no shim at $SHIM"
	exit 1
}
PYTHON="${PYTHON:-$(command -v python3)}"
[ -x "$PYTHON" ] || {
	echo "FAIL - no python3 on PATH"
	exit 1
}

# --- one sandbox machine: stub guard, stub confiner, stub real CLI ----------
# The guard answers help/version; the confiner would perform a global write; the
# CLI on PATH stands for whatever resolve_cli() finds. Their output is the
# evidence of which of the three actually ran.
home="$TMP/home"
mkdir -p "$home/.agents/bin" "$home/.agents/available-skills" "$TMP/cli"
cat >"$home/.agents/bin/aubx" <<'STUB'
#!/usr/bin/env bash
echo "GUARD-STUB: $*"
exit 0
STUB
cat >"$home/.agents/bin/aubx-skills" <<'STUB'
#!/usr/bin/env bash
echo "CONFINER-STUB: $*"
exit 0
STUB
cat >"$TMP/cli/skills" <<'STUB'
#!/usr/bin/env bash
echo "CLI-STUB: $*"
exit 0
STUB
chmod +x "$home/.agents/bin/aubx" "$home/.agents/bin/aubx-skills" "$TMP/cli/skills"

run_shim() { # run_shim <logfile> <args...>
	local log="$1"
	shift
	PATH="$TMP/cli:$PATH" HOME="$home" AGENTS_HOME="$home/.agents" \
		"$SHIM" "$@" >"$log" 2>&1
}

# --- help and version answer through the guard, never the npx fallback -----
for flag in --version -V --help -h; do
	run_shim "$TMP/h.log" "$flag"
	rc=$?
	assert "\`skills $flag\` exits 0" "[ $rc -eq 0 ]"
	assert "\`skills $flag\` answers through the guard" "grep -q 'GUARD-STUB' '$TMP/h.log'"
	assert "\`skills $flag\` never resolves the real CLI" "! grep -q 'CLI-STUB' '$TMP/h.log'"
done

run_shim "$TMP/bare.log"
rc=$?
assert "bare \`skills\` exits 0" "[ $rc -eq 0 ]"
assert "bare \`skills\` answers through the guard" "grep -q 'GUARD-STUB' '$TMP/bare.log'"

# --- the verbs that write harness roots are refused, not forwarded --------
for verb in sync experimental_sync experimental_install; do
	run_shim "$TMP/s.log" "$verb" </dev/null
	rc=$?
	assert "\`skills $verb\` exits 2" "[ $rc -eq 2 ]"
	assert "\`skills $verb\` names the roster it protects" "grep -q 'available-skills' '$TMP/s.log'"
	assert "\`skills $verb\` says the verb cannot be confined" "grep -qi 'cannot be confined' '$TMP/s.log'"
	assert "\`skills $verb\` runs no guard, confiner or CLI" \
		"! grep -qE 'GUARD-STUB|CLI-STUB|CONFINER-STUB' '$TMP/s.log'"
done

# --- a list-only add writes nothing, so it passes through read-only -------
for flag in -l --list; do
	run_shim "$TMP/l.log" add "$flag"
	rc=$?
	assert "\`skills add $flag\` exits 0" "[ $rc -eq 0 ]"
	assert "\`skills add $flag\` answers through the guard" "grep -q 'GUARD-STUB' '$TMP/l.log'"
	assert "\`skills add $flag\` never runs the confiner" "! grep -q 'CONFINER-STUB' '$TMP/l.log'"
done

# --- a confined write still routes to the confiner ------------------------
run_shim "$TMP/w.log" add demo/repo -g -y
rc=$?
assert "a global add still exits 0" "[ $rc -eq 0 ]"
assert "a global add still runs the confiner" "grep -q 'CONFINER-STUB: skills add demo/repo -g -y' '$TMP/w.log'"

# --- resolve_cli() cannot hand back this shim or a mise shim -------------
# Loaded as a module so each case can supply its own PATH; a subprocess cannot
# vary PATH for the module's own import-time constants as precisely.
cat >"$TMP/resolve.py" <<'PY'
import importlib.machinery
import importlib.util
import sys
loader = importlib.machinery.SourceFileLoader("skills_shim", sys.argv[1])
spec = importlib.util.spec_from_file_location("skills_shim", sys.argv[1], loader=loader)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("\n".join(module.resolve_cli()))
PY
resolved() { # resolved <shim-path> <path-value>
	# python3 by absolute path: $2 replaces PATH wholesale, so a lookup cannot work.
	PATH="$2" HOME="$home" AGENTS_HOME="$home/.agents" "$PYTHON" "$TMP/resolve.py" "$1"
}

# A second link to this same file, in a directory that is not SELF_DIR.
mkdir -p "$TMP/shimdir" "$TMP/alias" "$TMP/mise/shims"
cp "$SHIM" "$TMP/shimdir/skills"
chmod +x "$TMP/shimdir/skills"
ln -sfn "$TMP/shimdir/skills" "$TMP/alias/skills"
cat >"$TMP/mise/shims/skills" <<'STUB'
#!/usr/bin/env bash
echo "MISE-SHIM: $*"
exit 0
STUB
chmod +x "$TMP/mise/shims/skills"
got="$(resolved "$TMP/shimdir/skills" "$TMP/alias:$TMP/mise/shims:$TMP/cli")"
assert "a second link to this shim is skipped" "[ '$got' = '$TMP/cli/skills' ]"
assert "a mise/shims entry is skipped" "! printf '%s' '$got' | grep -q 'mise/shims'"

# A launcher whose link name is `mise` hands back whatever mise manages.
mkdir -p "$TMP/tools" "$TMP/links"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/tools/mise"
chmod +x "$TMP/tools/mise"
ln -sfn "$TMP/tools/mise" "$TMP/links/skills"
got="$(resolved "$TMP/shimdir/skills" "$TMP/links:$TMP/cli")"
assert "a link whose target is named mise is skipped" "[ '$got' = '$TMP/cli/skills' ]"

# The shim's own directory is still skipped, as before.
got="$(resolved "$TMP/shimdir/skills" "$TMP/shimdir:$TMP/cli")"
assert "SELF_DIR is still skipped" "[ '$got' = '$TMP/cli/skills' ]"

# --- every child is time-bounded; a stall reports 124 --------------------
mkdir -p "$TMP/slow"
cat >"$TMP/slow/skills" <<'STUB'
#!/usr/bin/env bash
sleep 30
STUB
chmod +x "$TMP/slow/skills"
start=$(date +%s)
PATH="$TMP/slow:$PATH" HOME="$home" AGENTS_HOME="$home/.agents" SKILLS_SHIM_TIMEOUT=2 \
	timeout 20 "$SHIM" list >"$TMP/t.log" 2>&1
rc=$?
end=$(date +%s)
assert "a stalled child exits 124" "[ $rc -eq 124 ]"
assert "the stall is reported, not silent" "grep -q 'timed out' '$TMP/t.log'"
assert "the bound is configurable" "[ $((end - start)) -lt 15 ]"

if [ "$fail" -eq 0 ]; then
	echo "all skills-shim hardening checks passed"
else
	echo "FAILURES"
	exit 1
fi
