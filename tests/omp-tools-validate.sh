#!/usr/bin/env bash
# Validate that every omp custom tool and extension loads, the way the omp
# host loads it (a module-graph import through bun). Catches the class of
# failure seen in ZYS-9134: a tool whose index.ts imports a sibling that does
# not exist or is not readable ("Failed to load tool: Cannot find module
# './tool.ts?mtime=…'"), which the live host only surfaces as a warning band.
#
# Runs on any machine with the agent dirs; a fresh CI runner has none, so the
# check is skipped there (exit 0) rather than failing on absent directories.
#
# Environmental notes, so the next editor does not re-derive them:
#   - `bun -e 'await import(<file>)'` evaluates the entry and every relative
#     import in its graph — the same resolution the omp host performs — and
#     exits non-zero with "Cannot find module '<specifier>' from '<file>'" on
#     the failing edge. Importing does not call the tool factory; a defect
#     that only appears when the factory runs with a live pi API is out of
#     scope here.
#   - Tools' `@oh-my-pi/pi-coding-agent` imports are type-only, so a bare bun
#     import evaluates the whole relative graph without a package install.
#   - Extensions may import host modules with runtime side effects. The host
#     binary bundles them; plain bun resolves them from the shared bun cache,
#     which does not carry the native addons. `Failed to load pi_natives
#     native addon` therefore means "validated outside the host process", not
#     a broken extension, and is reported as info, not failure. Every other
#     load error is a real defect.
set -uo pipefail

agent_dir="${OMP_AGENT_DIR:-$HOME/.omp/agent}"
tools_dir="$agent_dir/tools"
ext_dir="$agent_dir/extensions"
runner="$(command -v bun || true)"
failures=()
skipped=0
loaded=0
info_native=0

if [ -z "$runner" ]; then
	echo "FAIL: bun not found on PATH; it is the only loader that evaluates omp tool modules" >&2
	exit 1
fi

# check <entry-file> <label>: import the module graph in a subprocess.
# One module per process: a crash in one tool must not abort the scan.
check() {
	local entry="$1" label="$2" out status
	out="$("$runner" -e 'await import(process.argv[1])' "$entry" 2>&1)"
	status=$?
	if [ "$status" -eq 0 ]; then
		loaded=$((loaded + 1))
		return 0
	fi
	if printf '%s' "$out" | grep -q "Failed to load pi_natives native addon"; then
		# Host-provided native addon unavailable outside the omp binary: the
		# graph still resolved and evaluated up to that import.
		info_native=$((info_native + 1))
		return 0
	fi
	failures+=("$label (bun exit $status): $(printf '%s' "$out" | head -n 4 | tr '\n' ' ')")
	return 1
}

if [ -d "$tools_dir" ]; then
	for entry in "$tools_dir"/*.ts "$tools_dir"/*/index.ts; do
		[ -f "$entry" ] || continue
		check "$entry" "tool ${entry#"$tools_dir"/}"
	done
else
	skipped=$((skipped + 1))
	echo "info: no omp tools dir at $tools_dir; skipping tool validation"
fi

if [ -d "$ext_dir" ]; then
	for entry in "$ext_dir"/*.ts "$ext_dir"/*/index.ts; do
		[ -f "$entry" ] || continue
		check "$entry" "extension ${entry#"$ext_dir"/}"
	done
else
	skipped=$((skipped + 1))
	echo "info: no omp extensions dir at $ext_dir; skipping extension validation"
fi

if [ "${#failures[@]}" -gt 0 ]; then
	for f in "${failures[@]}"; do
		echo "FAIL: $f" >&2
	done
	exit 1
fi

echo "ok: $loaded omp modules imported cleanly ($info_native host-natives-only, $skipped dir(s) absent)"
exit 0
