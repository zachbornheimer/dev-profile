---
name: omp-hooks-before-agent-start-rerun
description: "Use when omp fails with \"System prompt changed repeatedly during before_agent_start; original input was not delivered\", or when editing a UserPromptSubmit/before_agent_start hook in ~/.omp/agent/extensions/hooks that calls setActiveTools or a model."
---

## Gotcha
omp re-runs `before_agent_start` handlers for the SAME prompt whenever the system prompt changed while they ran, and aborts after a few tries (`AgentStartPolicyChangedError` in `packages/coding-agent/src/session/agent-session.ts`). Anything a hook does that changes the tool list (`pi.setActiveTools`) changes the system prompt, so a non-deterministic hook loops.

## Observed cause (2026-11-09, session 01a1c17b)
`~/.local/state/omp-hooks/onUserPromptSubmit.jsonl` showed one 110-char prompt firing 3x in ~10s with active tool count 32, 33, 32: the model-picked tool suggestions differed per run and `sync_active_tools` replaced the active set each time.

## Rules for hooks in `~/.omp/agent/extensions/hooks/`
- Tool activation is sticky per session: the active set only grows (`prompt_hooks/sync_active_tools.ts`). Never shrink it per prompt.
- `prompt_submit.ts` `onPrompt` memoizes the result per (session_id, hash of prompt) for 120s and replays it on re-runs: no second model call, no second setActiveTools.
- Hooks must never spawn `omp -p` as a fallback (multiplies load across concurrent sessions); model steps are in-process only.
- Diagnose by grepping the log by session id and prompt_chars: repeated rows with differing `active_tools` = this loop. Look for `replayed: true` to confirm the fix works. Use `tail -n 400 | jq`, not jq on the whole file (it is huge and times out).
- Tests: `cd ~/.omp/agent/extensions/hooks && bun test hooks.test.ts self_contained.test.ts`.
