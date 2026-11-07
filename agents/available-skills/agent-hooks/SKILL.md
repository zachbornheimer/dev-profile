---
name: agent-hooks
description: >-
  Operate the agent-hooks system (~/Developer/Personal/agent-hooks): a Rhai handler pipeline whose live
  deployment (~/.config/agent-hooks/pipeline) runs guards and gates for the harnesses installed on this
  machine — omp (through the generated extension) and Claude Code — and can install into Codex, Gemini,
  Grok, Hermes, Copilot, OpenCode or Mastra if one returns. Use it to pick the event an intent belongs on
  (behavior from user input -> prompt.submit; may the turn stop -> turn.stop; allow/deny/rewrite a tool
  call -> tool.before; react to a tool result -> tool.after; session setup -> session.start; survive
  compaction -> context.compact.before; verify a subagent -> subagent.stop; worktree lifecycle ->
  worktree.create/remove), and whenever the user adds, edits, tests,
  deploys, or debugs a hook, guard, or gate: a PreToolUse deny/ask, scope guard, edit/tool steer,
  PostToolUse record, Stop completion gate, UserPromptSubmit or SessionStart context, PreCompact;
  Rhai handlers under pipeline/handlers; fixtures under pipeline/tests; question YAML under
  pipeline/questions; capabilities/effects; the question-pipeline ask flow; `mise run deploy-pipeline`;
  AGENT_HOOKS_DUMP_* / DEBUG_ASK diagnostics; the hooks.toml dispatch rows; or a hook that "did not
  fire", "fired twice", "blocked with the wrong reason", "failed open", "panicked / exit 101", or
  "compiled but the fixtures fail". NOT for git hooks (husky, lefthook, pre-commit, zq), worktrunk `wt`
  hooks or "a hook denied my git command, what is the allowed alternative" (worktrunk-index), React
  hooks, webhooks, or TypeSafe question wording/threshold tuning (typesafe-ai-effective-use).
---

# agent-hooks

Two layers, one repo (`~/Developer/Personal/agent-hooks`):

1. **Dispatch** — `~/.config/agent-hooks/hooks.toml` rows point each harness event at a policy. The
   pipeline rows are minimal: `name = "pretooluse-question-pipeline"`, `events = ["tool.before"]`,
   `policy = "question-pipeline"`, `timeout = "28s"` (plus stop and prompt.submit rows). No `command`,
   no matcher: the pipeline sees every call and filters per handler.
2. **Logic** — the Rhai pipeline: `pipeline/handlers/*.rhai` (one file per hook), `pipeline/questions/*.yaml`
   (model questions), `pipeline/capabilities/*.toml` + `effects` (external work), `pipeline/ask-mastra.sh`
   (the live asker). Deployed to `~/.config/agent-hooks/pipeline/` by `mise run deploy-pipeline`, which
   also regenerates the live `pipeline.toml` (handlers list is auto-derived from the handlers dir — no
   registration edit needed) and installs the `agent-hooks` binary via cargo.

| If the task is                                        | Go to                                                    |
| ----------------------------------------------------- | -------------------------------------------------------- |
| add or edit a hook (the main workflow)                | Add or change a hook (steps 1-8)                         |
| handler authoring: metadata block, input fields, deny | Handler anatomy                                          |
| fixture shape, seeding, answers                       | Fixture contract                                         |
| asking a model question from a handler                | Questions and the ask pipeline                           |
| external commands / scripts from a handler            | Capabilities and effects                                 |
| Rhai code that won't compile or behaves oddly         | Engine notes (Rhai is not Python)                        |
| a hook did not fire / wrong reason / failed open      | Debugging                                                |
| non-pipeline `command` rows, matchers, output shapes  | Legacy script rows, `references/events-and-harnesses.md` |

## Pick the event from the intent

Read the left column first: the intent picks the event, and the event decides what the hook is allowed to
do. Full per-harness names and quirks: `references/events-and-harnesses.md`.

| When you want to …                                                                  | Event (canonical / native)               | The hook may                                                                                       |
| ----------------------------------------------------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| change behavior from what the user typed (classify, add context, reject the prompt) | `prompt.submit` / UserPromptSubmit       | inject context, **block** the prompt                                                               |
| decide whether a finished turn may stop (completion gate, keep-working nudge)       | `turn.stop` / Stop                       | **block** (the agent keeps working), context                                                       |
| allow, ask about, or reject a tool call, or rewrite its arguments                   | `tool.before` / PreToolUse               | deny, ask, allow, rewrite tool input                                                               |
| react to a tool's result (record it, steer the next call, budget the output)        | `tool.after` / PostToolUse               | context only                                                                                       |
| catch a denied or failed tool call                                                  | `PermissionDenied`, `PostToolUseFailure` | context only (Claude-only event names)                                                             |
| set a session up (identity, recall, contracts)                                      | `session.start` / SessionStart           | context only                                                                                       |
| preserve state across compaction (handoff, save transcript)                         | `context.compact.before` / PreCompact    | context only                                                                                       |
| verify or score what a subagent returned                                            | `subagent.stop` / SubagentStop           | context only                                                                                       |
| prepare a worktree before an agent starts in it                                     | `worktree.create` / WorktreeCreate       | stdout is the bare path; **exactly one** hook may `provides = ["worktree_path"]`; cannot fail open |
| clean up after a worktree is removed                                                | `worktree.remove` / WorktreeRemove       | **blockable**; a hook whose result nobody consumes belongs in the background                       |

Two rules that keep this maintainable:

1. **A judgment goes in Rhai; a boundary stays a command.** If the hook decides something, it is a handler
   on one of these events. If it only spawns a process, waits on a CLI, or carries a model call, it is a
   `command` row or an effect — never a judgment buried in a script (the retention ledger in `SPEC.md` says
   which commands stay and why).
2. **One owner hook per (event, state).** The dispatcher cannot sequence hooks: every matching hook starts
   at once and they share nothing, so "ask, then act on the answer" has to live inside a single owner hook
   as waves — adding a second hook for the same event does not compose, it races. Read
   `references/typesafe-batching.md` before adding questions; ask the owner's question file instead.

## Add or change a hook (in order)

Work on a branch, never in the main checkout (main is protected; `wt` enforces it):

```bash
cd ~/Developer/Personal/agent-hooks && wt tree-for-changes <slug>
# edit inside the created ~/Developer/Personal/.worktrees/agent-hooks-<uuid>
```

1. **Write the handler** `pipeline/handlers/<stage>-<name>.rhai` — see Handler anatomy. File basename IS
   the hook name; it auto-registers at deploy.
2. **Write fixtures** `pipeline/tests/<hook-name>/<case>.json` — one JSON per case, see Fixture
   contract. Fixtures are ground truth: prefer changing the handler over the fixture, and change a
   fixture only when it contradicts the harness contract.
3. **Test the hook alone** (harness lives in the main checkout; filters match HOOK names only, never
   fixture case names):

   ```bash
   cd ~/Developer/Personal/agent-hooks && \
     AGENT_HOOKS_PIPELINE_DIR=<your worktree>/pipeline cargo test --test handlers -- <hook-name>
   # green = "test result: ok. N passed; 0 failed" and exit 0 — print ${PIPESTATUS[0]} if you pipe
   ```

4. **Run the full suite** to catch cross-hook drift: `cargo test --test handlers` (main checkout).
5. **Commit** in the worktree: `git add <files> && git commit -S -m "<type>(pipeline): ..."`
   (conventional, signed, no attribution trailers). Review the diff before merging — stray debug
   blocks have ridden along in merges before (`input.block = dbg` shipped live for two minutes once).
6. **Merge**: `wt merge -y main` from the worktree, then `git push origin main` from the main checkout.
   If the merge hits conflicts, resolve to main's side when main is a superset.
7. **Deploy**: `mise run deploy-pipeline` (script `scripts/deploy-pipeline.sh`). It syncs handlers,
   questions, capabilities, effects, and ask-mastra.sh to the live dir, reinstalls the binary, runs
   validate + a smoke probe, and REFUSES an unhealthy deploy. Run it after every green merge.
8. **Prove it live** on one real event (a deliberate probe in a scratch session), then read the
   state log the handler appends.

## Handler anatomy

```rhai
// One paragraph: what the hook stops or injects, and why. The guard's deny text
// must name the alternative, not just the refusal.
#{
    stage: "PreToolUse",          // PreToolUse | PostToolUse | Stop | UserPromptSubmit | SessionStart | PreCompact
    priority: 10,                 // lower runs earlier inside the chain
    tools: "^(Edit|Write|bash)$", // regex over the tool name; omit to see all tools
    on_error: "block",            // a handler that dies still stops the edit
    handle: |input, data, next| {
        let raw = input.tool_name;   // string
        if type_of(raw) != "string" { raw = ""; }
        let ti = input.tool_input;   // map (the tool's arguments)
        let cwd = input.cwd;         // string

        // deny: set input.block and return input. The text is shown to the model;
        // say what to do instead, name the replacement tool or command.
        input.block = "Built-in X is disabled here; use Y instead.";
        return input;

        // otherwise pass to the next handler in the chain
        next.call(input)
    },
}
```

Facts that bite:

- `input.tool_name`, `input.tool_input` (map), `input.cwd` are the useful request keys. Probe any
  nested value with `type_of(...)` guards before string ops — the harness feeds raw harness payloads.
- A deny is `input.block = "<reason>"` + `return input`. Everything else is `next.call(input)`.
  A handler that neither blocks nor calls next silently ends the chain.
- `on_error: "block"` makes an exception/compile error in the handler deny the call instead of
  fail-open — use it for guards, not for context injectors.
- State: `state_set(scope, key, value)` stores JSON text; `state_get(scope, key)` PARSES it back
  (returns unit when missing); `state_append(log_name, record)` appends a record to a JSONL ledger
  (e.g. `scope-judgments`). Round-trip through strings, not raw arrays.
- To ask the model questions: `ask(...)` (see Questions below). To run external work:
  `capability("<name>", args)` (see Capabilities).
- `home()` returns the seeded HOME (fixtures seed it via `"env"`); resolve relative paths against
  `input.cwd` yourself.

## Fixture contract

One JSON file per case under `pipeline/tests/<hook-name>/`. Each fixture runs its hook ALONE (that is
the contract — fixtures were captured standalone); add `"with": ["other-hook"]` to chain more handlers
ahead of it. Shape (all keys seen in the live suite):

```json
{
  "input": {
    "stage": "PreToolUse",
    "event": {
      "session_id": "s1",
      "cwd": "/tmp",
      "hook_event_name": "PreToolUse",
      "tool_name": "Edit",
      "tool_input": { "path": "/sg-work/Developer/repo/src/a.rs" }
    }
  },
  "env": { "HOME": "/sg-work" },
  "clock": { "now_epoch": 1793650800 },
  "state": { "session": { "scope-asks": [] } },
  "answers": { "scope-guard-tool.yaml#OffTopic": 0.05 },
  "expect": { "block": "exact deny text" }
}
```

- `"expect": {}` means pass-through (no block, no error).
- `"expect": { "appended": { "<ledger>": [ { "...": "exact records" } ] } }` asserts state appends.
- `"answers"` keys are `"<question file>#<asked text>"` -> numeric/string answer; seeded because
  scope-guard-tool.yaml and scope-guard-stop.yaml share identical question text and answers route
  per (file, text).
- `"state"` seeds namespaced state (`{"session": {...}}` is what `state_get("session", ...)` reads).
- `"clock"` fixes timestamps; `"env"` fixes `home()`.
- Prefer fixing the handler; fixtures are the recorded behavior. If the user explicitly overrules a
  recorded behavior, update the fixture in the same change and say so in the commit message.

## Questions and the ask pipeline

- Question files `pipeline/questions/<name>.yaml` declare the questions a hook asks (id + asked text +
  choice record like `choices: {"true": "", "false": ""}` — choices are a RECORD of value->text, never
  an array) and route to an asker.
- The host batches **one ask per event**: all questions from all handlers in the chain go in one
  request. Answers come back as `{qid: answer}`.
- The wire contract: the backend (`ask-mastra.sh` -> `capability run prompt_submit_questions`, 15 s
  per pipeline.toml) receives `{state, questions: [{id, question, choices}]}` — NO `file` field; the
  host strips its internal routing key before calling the backend (a leaked `file` key made the
  capability misparse every question as a file reference and all live answers read as defaults, so
  the guard allowed everything).
- A failed asker reads as defaults — design handler thresholds so defaults fail SAFE (deny) for
  guards, fail open for context hooks.
- Debug ask wiring live: `AGENT_HOOKS_DEBUG_ASK=1` plus `-- --nocapture` prints
  `ask: keyed=... answers=...`.

## Capabilities and effects

`capability("<name>", args)` runs an external tool declared in `pipeline/capabilities/*.toml`; heavier
scripts live under `pipeline/effects/`. Handlers must treat a capability reply of `()`/empty as
"unknown" and decide explicitly (fail open or closed per the hook's fixtures) — see the goals-recall
handler for the pattern.

## Engine notes (Rhai is not Python)

- Strings are immutable: `trim(s)`/`replace(s, a, b)` here are PURE — they return new strings (the
  host registered them; rhai builtins mutate in-place). Assign the result.
- `to_lowercase`/`to_uppercase` exist. Top-level `const NAME = value;` works (the host converts consts
  to functions and rewrites references — named `fn`s cannot see script consts, so prefer consts).
- Use `type_of(x)` before method calls on `Dynamic` values; `starts_with`/`ends_with`/`contains`,
  array `.len()`, map indexing are available.
- Compile failures dump per-handler transformed source with
  `AGENT_HOOKS_DUMP_HANDLERS=/tmp/dir cargo test ...`; the combined AST with
  `AGENT_HOOKS_DUMP_SCRIPT=/tmp/x.rhai`.

## Debugging (stop at the first step that explains it)

1. **Which binary, which pipeline?** Live deployment is `~/.config/agent-hooks/pipeline` at the last
   `mise run deploy-pipeline` ref — main-checkout edits do nothing live until deployed. Check the
   dispatch row exists in `~/.config/agent-hooks/hooks.toml` for that event.
2. **Fixtures green but live wrong** -> usually the asker: run
   `echo '{"state":{"user_message":"t"},"questions":[{"id":"q0","question":"t?","choices":{"true":"","false":""}}]}' | bash ~/.config/agent-hooks/pipeline/ask-mastra.sh`
   and expect an answers map (exit 0). Empty output + nonzero exit = every answer defaulted.
3. **Did the handler see the payload you think it did?** Drop the DUMP_SCRIPT/DUMP_HANDLERS env vars
   and read the transformed source; run the single-hook fixture test with `-- --nocapture`.
4. **Fired twice / merged reason from another hook** — the pipeline aggregates: strongest effect
   wins, the FIRST reason in chain order is surfaced. Give every blocking handler a self-contained
   deny text.
5. **Exit 101** is a Rust panic in the host (e.g. context length cap), not your handler.
6. Stale binary: `which -a agent-hooks`; deploy reinstalls via cargo.

## Legacy script rows

After the Rhai cutover the live `hooks.toml` is 20 rows: 8 `policy = "*-question-pipeline"` rows (the
handler pipeline), 9 Rust-native `policy` rows (`layout-guard`, `layout-guard-write`,
`record-bash-signature`, `record-edit`, `output-budget`, `output-limit`, `repeat-command`,
`two-strikes-gate`, `worktree-lifecycle-guard`), and 3 `command` rows that stay external on purpose:
`stop-find`, `worktreeremove-wt-step-prune`, and `worktreecreate-worktree-provision-py` (the only row
with `provides = ["worktree_path"]`, and the only one that cannot be backgrounded). Every other hook
that used to be a Python row is now a handler; do not add a command row for a judgment.

The `SPEC.md` retention ledger is the authority on which commands stay and the condition for porting
each. A ported policy's Python original is NOT dead code: it is the reference the native policy is
judged against (`POLICY_SCRIPTS`, re-executed by the `--ignored` `live_reference_decisions_still_match`,
which skips silently if the reference directory is missing — deleting an original drops the check).

Retiring a live row has a recorded standard: parity green across its full fixture set including live
re-validation with `AGENT_HOOKS_REFERENCE_DIR` set to the Python hook directory, no `failed`/`timed_out`
journal outcome for that hook over a defined window, and an explicit retirement decision recorded in
`atask`. Retired names are pinned in `tests/pipeline_coverage.rs` (`RETIRED_ROWS`), so a retired row
cannot come back unnoticed.

Rows keep the OLD rules: `matcher` is an exact case-sensitive name list split on `|` (never a regex);
hooks are independent parallel processes; default is fail-open; `agent-hooks validate` misses unknown
keys, duplicate names (a same-name row silently REPLACES), event typos, and command-less rows — run the
audit: `~/.agents/available-skills/agent-hooks/scripts/audit-catalog.py [file]`. Output shapes per
harness and event vocabularies: `references/events-and-harnesses.md`. Dated defects:
`references/known-issues.md`. Python-row authoring (uv script header, `hook_common.run_hook`,
`Decision.deny`) survives only in the remaining command rows — new hooks go in the Rhai pipeline.
