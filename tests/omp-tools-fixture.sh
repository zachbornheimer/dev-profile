#!/usr/bin/env bash
# Exercise the public health command against real module graphs, not mocked loaders.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
export OMP_AGENT_DIR="$scratch/agent"
mkdir -p "$OMP_AGENT_DIR/tools/example" "$OMP_AGENT_DIR/extensions"
check=(bash "$root/tests/omp-tools-validate.sh")
fail() {
	cat "$scratch/output" >&2
	echo "FAIL: $*" >&2
	exit 1
}
expect_failure() {
	if "${check[@]}" >"$scratch/output" 2>&1; then fail "$1 was accepted"; fi
	grep -Fq "$2" "$scratch/output" || fail "$1 lacked a useful diagnostic"
}
cat >"$OMP_AGENT_DIR/tools/example/index.ts" <<'TS'
import { description } from './tool.ts';
export default function makeTool() { return { description }; }
TS
cat >"$OMP_AGENT_DIR/tools/example/tool.ts" <<'TS'
export const description = 'healthy';
TS
"${check[@]}" >"$scratch/output" 2>&1 || fail "valid relative graph failed"
rm "$OMP_AGENT_DIR/tools/example/tool.ts"
expect_failure "missing sibling" 'tool.ts'
cat >"$OMP_AGENT_DIR/tools/example/index.ts" <<'TS'
export default 42;
TS
expect_failure "non-callable factory" 'default export'
cat >"$OMP_AGENT_DIR/tools/example/index.ts" <<'TS'
throw new Error('Failed to load pi_natives native addon: fixture');
export default function makeTool() {}
TS
expect_failure "native addon failure" 'pi_natives'
cat >"$OMP_AGENT_DIR/tools/example/index.ts" <<'TS'
export default function (
TS
expect_failure "syntax error" 'example'
if command -v omp >/dev/null 2>&1; then
	rm -rf "$OMP_AGENT_DIR/tools/example"
	cat >"$OMP_AGENT_DIR/extensions/broken.ts" <<'TS'
export default function install() { throw new Error('fixture-registration-failed'); }
TS
	expect_failure "extension registration failure" 'fixture-registration-failed'
fi
echo 'ok: omp health rejects broken graphs, invalid factories, native failures, and registration failures'
