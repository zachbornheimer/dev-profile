---
name: omp-self-contained-hooks-gotchas
description: "Editing ~/.omp/agent/extensions (onUserPromptSubmit, onStop, onSubagentStop, onPreToolUse, hooks/*, prompts/*): unified hook() + ctx.inquiry() architecture, homework/preference-avoidance Stop policy, and import boundary rules"
---

# omp Self-Contained Hooks & Extensions

Editing `~/.omp/agent/extensions` (`onUserPromptSubmit.ts`, `onStop.ts`, `onSubagentStop.ts`, `onPreToolUse.ts`, `hooks/*`, `prompts/*`).

## Architecture (verified 2026-11-12)

All 4 active hook extensions (`onUserPromptSubmit.ts`, `onStop.ts`, `onSubagentStop.ts`, `onPreToolUse.ts`) use the same single-responsibility pattern:
1. Top-level `extensions/on*.ts` passes `name: HOOK, stage: STAGE, event, ctx: () => withInquiry(rawCtx), questions: QUESTIONS, inquiryInput, run` to `hook()` from `./hooks/log.ts`.
2. Questions live in YAML files under `extensions/prompts/` (and mirrored to `~/.omp/agent/prompts/`):
   - `onUserPromptSubmit.ts`: `prompts/dictation.yaml`, `prompts/frustration.yaml`, `prompts/intent.yaml`, `prompts/suggest.yaml`, `prompts/rewrite-dictated.yaml`.
   - `onStop.ts` & `onSubagentStop.ts`: `prompts/stop.yaml` (13 `noul` questions answered in one ~200ms System One batch).
   - `onPreToolUse.ts`: `prompts/pre-tool-use.yaml` (3 `noul` questions answered in one System One batch).
3. Shared `hooks/` modules (zero `../prompts/*` imports, enforced by `hooks/self_contained.test.ts`):
   - `hooks/log.ts`: `hook()` middleware, `toProbability`, `meetsThreshold`, `wrapProbabilityAnswers`, `withDeadline` around `ctx.inquiry` (`deadlineMs ?? 8500`), automatic `stage`/`omp_event` logging, `OMP_HOOKS_LOG_DIR` and `OMP_HOOKS_STATE_DIR` support.
   - `hooks/transcript.ts`: `readSessionTranscript(session)` (retains `prompts[0]` initial task + last 6 follow-up prompts across `.jsonl` and `scope-asks-<session_id>.jsonl`).
   - `hooks/ledger.ts`: per-session TSV rejection/correction ledgers (`stop-reject-<session_id>.tsv`, `scope-corrections-<session_id>.tsv`) and `completion-gate-judgments.jsonl`.
   - `hooks/turn_stop.ts`: `prepareStopInquiry`, `decideTurnStop` (`evaluateDeferralBlock`, `evaluateClaimAndScopeBlock`), `onTurnStop`.
   - `hooks/tool_use.ts`: `prepareToolInquiry`, `decidePreToolUse`, `isReadOnlyTool` (unwraps `tool_call` `skill/*` and read-only `omp/*` tools including `wait`), `isJobCollectOnly` (skips `run_command` `{ jobId }` collection in 0ms), `onTool`.

## Stop / Homework Policy (`extensions/hooks/turn_stop.ts` + `prompts/stop.yaml`)

- **Preference questions never excuse unfinished work:** Only `user_withheld_action >= 0.50` excuses deferred work. Asking a preference question (`uses_preference_to_avoid_work >= 0.55`, `leaves_doable_work >= 0.60`, `stopped_investigation >= 0.55`, `defers_doable_work >= 0.50`, `prework_before_handoff >= 0.75`) blocks the turn and instructs the agent to resolve in-scope obstacles and finish all doable work first, then pin any remaining user-only fork with `pin_decision`.

## Verification

Whenever editing `extensions/prompts/*.ts` or `extensions/prompts/*.yaml`, sync them to `~/.omp/agent/prompts/` and run:
`cd ~/.omp/agent/extensions && bun test hooks/hooks.test.ts hooks/user_prompt_submit.test.ts hooks/self_contained.test.ts prompts/prompts.test.ts`
