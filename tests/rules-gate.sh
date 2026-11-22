#!/usr/bin/env bash
# Run the installed TTSR rule fixture gate. The rule set is mise-dot tracked at
# $AGENT_DIR/rules and is not in this repository, so three states are decided here:
#   no omp install        -> SKIP, exit 0 (CI runner, scratch HOME)
#   install, no gate file -> FAIL, exit 1 naming the path
#   install with gate     -> run the gate and propagate its exit code
set -euo pipefail
AGENT_DIR="${OMP_AGENT_DIR:-$HOME/.omp/agent}"
gate="$AGENT_DIR/rules/rule_conditions.test.ts"
if [ ! -d "$AGENT_DIR" ]; then
	echo "SKIP: no omp install at $AGENT_DIR"
	exit 0
fi
if [ ! -f "$gate" ]; then
	echo "FAIL: omp install at $AGENT_DIR has no rule fixture gate: $gate" >&2
	exit 1
fi
exec bun test "$gate"
