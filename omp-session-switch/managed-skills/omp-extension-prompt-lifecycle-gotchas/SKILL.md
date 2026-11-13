---
name: omp-extension-prompt-lifecycle-gotchas
description: "Editing omp extensions that rewrite typed prompts via the input hook (e.g. ~/.omp/agent/extensions/read-only /ro): when a submitted prompt can still come back to the composer, and which events mark true delivery."
---

## Facts (verified in ~/Developer/Personal/oh-my-pi source, 2026-11-09)

- `~/.omp/agent/extensions/*` is NOT a git repo (no worktree possible); edit in place, then restart omp (`omp_restart`). No test harness exists (`extension-tests/` is empty) and `lsp` has no TS server for it.
- `input` hook runs in input-controller `onSubmit` (before `startPendingSubmission`), so everything downstream (pending submission, queue, DroppedPrompt) carries the REWRITTEN text, not what the user typed. An extension that rewrites (e.g. strips `/ro `) must remember `original` and re-prefix when omp hands the text back.
- omp hands text back to the composer three ways, none emit an extension event: `cancelPendingSubmission` (Esc before `started`), `restoreQueuedMessagesToEditor` (Esc/Alt+Up with queued msgs), and `setPromptDropped` -> `#restoreDroppedPrompt` (abort raced turn setup; only restores if composer is empty).
- `before_agent_start` is NOT delivery. After it, `#promptWithMessage` still awaits auto-thinking classification, pre-prompt compaction and prewalk, each with `#promptGeneration` checks that return false -> prompt dropped to composer. Treat the user-role `message_start` as the point of no return (and `turn_start` for "a turn ran"). Forgetting state in `before_agent_start` loses the rewrite on an early Esc.
- Handlers get a uniform `ctx` incl. `ctx.agent.kind`; guard `=== "main"` to ignore subagents.
