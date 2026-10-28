#!/usr/bin/env bash
# Runs one Hindsight coding-agents hook (`hindsight-hook.sh claude-hook.js`).
#
# omp reaches Hindsight only through the capability gateway, so its tools are not registered under their bare
# names there: they are catalog entries called with tool_call. On omp (AGENT_HOOKS_HOST=omp, set by
# run-agent-hooks.ts) the injected tool guide gains one line saying how to call them; every other host keeps
# the guide unchanged. An explicitly configured HINDSIGHT_TOOL_GUIDE_EXTRA is kept and the omp line appended.
set -u
hook=${1:?usage: hindsight-hook.sh <hook file in ~/.hindsight/coding-agents/dist>}
if [ "${AGENT_HOOKS_HOST:-}" = omp ]; then
	omp_line='In this harness the hindsight_* tools are reached through the capability gateway: call tool_call({ address: "hindsight/<tool name>", args }), e.g. tool_call({ address: "hindsight/hindsight_search_knowledge_pages", args: { query: "..." } }).'
	nl=$'\n'
	export HINDSIGHT_TOOL_GUIDE_EXTRA="${HINDSIGHT_TOOL_GUIDE_EXTRA:+${HINDSIGHT_TOOL_GUIDE_EXTRA}${nl}}${omp_line}"
fi
exec node "$HOME/.hindsight/coding-agents/dist/$hook"
