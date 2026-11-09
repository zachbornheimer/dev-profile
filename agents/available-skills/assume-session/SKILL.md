---
name: assume-session
description: Use whenever a prompt contains a session ref (grok|claude|codex|copilot|pi|omp|cursor|opencode|hermes:<id>, a bare id with a harness named, or `<harness>:latest`) or a Mastra thread URL — to fetch, read, analyze, review, summarize, or debug that session's transcript BY ID (read-only lookup, the default), or to take the session over and continue its work (`--then continue|confirm`). Also the entry for "analyze/look at/what happened in session omp:01a1…", "why did that session fail", "find out what session X did". Resolves the id through the capability tools (`get_recent_turns`, `create_session_handoff_doc`); never hand-grep session directories.
user-invokable: true
argument-hint: "<tool>:<session-id> | <mastra-thread-url>  [--then continue|confirm]   (omit --then to only read/analyze)"
---

# Assume Session

One entry point for any session ref (`omp:01a1c0b2-…`, `claude:<id>`, a Mastra
thread URL). It resolves the id to a transcript through the capability tools,
then does one of two things:

- **Lookup (default).** The user wants to _read, analyze, review, summarize or
  debug_ the session ("analyze omp:01a1…", "what did session X do", "why did it
  fail"). Fetch the transcript, answer the question asked, stop. No takeover, no
  `--then`, none of the takeover gates below.
- **Takeover.** The user passed `--then continue|confirm`, or said "assume",
  "take over", "continue that session", "pick up where it left off". Everything
  below the lookup section applies.

If the request is ambiguous between the two, do lookup: reading is reversible,
taking over someone's in-flight work is not. Never hand-grep
`~/.omp/agent/sessions`, `~/.claude/projects` or similar; the tools below find the
session from its id.

## Lookup mode (read-only transcript by ID)

Pass the ref exactly as given. After `<harness>:` it accepts a full id, a unique
prefix, `latest`, or title words. **`get_transcript` is the primary tool**: it
writes the whole session as a JSON Lines file (one `item` line per message, tool
call or tool result, with `turn` and `role`) that you `read`, `grep` or `jq`; add
`annotate: true` for per-item cost/waste/correction readings. In omp these are
native tools (`get_transcript`, `get_recent_turns`, `create_session_handoff_doc`,
`extract_hypotheses`, `learn_from_transcript`); in other harnesses the same tools
are `capability/run_<name>`.

| User wants                                                             | Call                                                                                                                  |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Read or search the whole transcript, answer a question about it        | `get_transcript` `{sources: ["<ref>"]}`, then `read`/`grep`/`jq` the `path` it returns (line 1 is the session header) |
| Just the last few turns inline                                         | `get_recent_turns` `{conversation, turns, length_limit, max_tokens}`                                                  |
| Where it stopped: cwd, branch, side effects, errors, last user message | `create_session_handoff_doc` `{conversation}` (read `context`)                                                        |
| Per-turn cost, waste, corrections, tokens                              | `get_transcript` `{sources: ["<ref>"], annotate: true}`, then read the `path` it returns (`annotation` on each line)  |
| Adversarial review: what the session wasted, how to do better          | `extract_hypotheses` `{sources: ["<ref>"]}`                                                                           |
| Turn a bad session into filed fixes                                    | `learn_from_transcript` `{source: "<ref>"}` (only when asked; it files tickets)                                       |
| Claude session's native transcript path, jobId or pid                  | the `find-session` skill                                                                                              |

Report what the transcript shows with turn numbers or verbatim quotes, and mark
inference as inference. An ambiguous prefix or title is refused with candidates:
relay them. A "no session found" error is final: do not guess another id.

## Takeover mode

Reads the transcript, **states what it understands your goal to be**, then
**takes over the work in this session** —
verifying the now-stale state and continuing where the other agent left off,
instead of handing you a document to paste. A required `--then` flag decides
whether it continues on its own or waits for your confirmation after stating the
goal. The synthesis stays in a subagent so this session's context is lean enough
to actually do the work.

## Hard stops on takeover (takeover mode only; lookup mode skips them)

- **Gate: the goal statement comes before any action.** After the capability
  returns the transcript (step 2), your very next output is the three-part block
  from step 3 — `Goal as I understand it` / `Where it stopped` / `What I would do first`
  — as plain text, then saved with the write tool to
  `/tmp/assume-<tool>-<short-id>-goal.md`. No shell command, edit or verification
  may run until that file exists, in `--then continue` mode too. Narrating an
  intent ("I'll now check…") is not the block.
- **Gate: the premise re-derivation comes before any inherited work.** No step
  of the inherited plan runs until the step-6b premise gate passes — the
  original user symptom restated verbatim, the plan's falsifiable premises
  checked against current world state, the floor compared, and the owner's
  config surface searched. Approval does not waive it: it applies in both
  `--then continue` and `--then confirm` modes, and a user's
  "yes"/confirmation lifts nothing. A plan whose premises survive is continued
  as-is; a falsified premise is stated and the plan is fixed, not
  abandoned.
- Do not start a new project and do not treat this as a fresh chat.
- Finish the work that was in flight. Do not rotate onto a side quest.
- Before any risky edit: snapshot the tree (WIP-commit or stash). Do not discard dirty files.
- If this session was blocked on access — aws-vault, 1Password, SSO, expired creds — try that first, now.

## How to invoke

```text
/assume-session omp:01a1c0b2-1775-76e8-adc1-ab04fb9d04f4            # lookup: read/analyze only
/assume-session claude:663aeacb why did it stall?                    # lookup with a question
/assume-session claude:663aeacb-9509-4229-8c87-c248defeac34 --then confirm
/assume-session grok:01a020ee-d80c-7540-a2fe-a4a518d46c2e --then continue
/assume-session codex:able-efgh-1234 --then confirm
/assume-session copilot:014575b7-cc61-4292-84cb-7d26fcc29d2f --then confirm
/assume-session pi:<id> --then continue
/assume-session omp:<id> --then continue
/assume-session grok:latest --then confirm
/assume-session cursor:DevOps conformance rollout review --then confirm
/assume-session claude:663aeacb --then confirm
/assume-session https://stable.capability-replicas.localhost/agents/code-improver/threads/a3927124-9c47-4d02-b417-133c06c71385 --then confirm
```

Two reference forms:

- `<harness>:<id>` — harness is one of `grok`, `claude`, `codex`, `copilot`, `pi`,
  `omp` (also `cursor`, `opencode`, `hermes`).
- A Mastra chat-thread URL, `https://<host>/agents/<agentId>/threads/<threadId>`
  (the capability reads it as `mastra:thread:<threadId>`).

For takeover, `--then` is **required** (lookup mode has no `--then`):

| Value      | After step 2                                                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------ |
| `continue` | Write the goal statement (step 3), then go straight on to the brief and the takeover in the same turn. |
| `confirm`  | Write the goal statement (step 3), then stop and wait for the user to confirm or correct it.           |

The goal statement is **mandatory in both modes** and comes first. Reading the
transcript and then going straight to commands, edits or verification is a
defect — the user must be able to see what you took the goal to be before you act on it.

`--then` only gates the start of the takeover. The step-6b premise
re-derivation gate and step 6d (confirm before any irreversible action) apply
in both modes — a user's confirmation waives neither.

## Steps

1. **Parse the argument.** Take the reference (a `<harness>:<id>` ref or a Mastra
   thread URL) and, if present, `--then`. If the reference has no harness prefix
   and is not a URL, infer the harness from the id's shape or the session you are
   in (an `01a…` uuid with `omp` mentioned is `omp:<id>`); ask only if it is
   still unknown. No `--then` and no takeover wording means lookup mode: follow
   "Lookup mode" above and skip the rest of this list. `--then` present but not
   `continue`/`confirm`, or takeover wording without it, means ask the user for it
   (one question, two options) — never default a takeover.

2. **Deliver the transcript through the capability MCP.** The capability finds
   the session and normalizes the URL itself; pass the reference exactly as given
   in `conversation`. After `<tool>:` it accepts a full id, a unique id prefix,
   `latest` (newest top-level session), or words from the session's title (cursor,
   grok, omp, copilot, hermes, opencode). An ambiguous prefix or title is refused
   with the candidates listed; relay them and ask which one. Do not run a locator
   script first. The result's `conversation` field carries the resolved full id —
   use that id from here on.

   - `capability/run_get_recent_turns` — `{"conversation": "<ref-or-url>", "turns": 40, "max_tokens": 20000}`.
     Returns role-labeled human/agent turns (hook feedback and other harness
     machinery are not in them) with timestamps and `source.path`.
     For the whole session raise `turns`, `length_limit` and `max_tokens`; there is no maximum.
   - `capability/run_create_session_handoff_doc` — `{"conversation": "<ref-or-url>"}`.
     Returns the handoff markdown and a structured `context` (`working_dir`,
     `git_branch`, `worktrees`, `other_projects`, `git_status`, `last_user_message`,
     `test_status`, `session_end`, `errors_seen`, `side_effects`), computed without
     a model and with native cwd/branch where the harness records them. Grok
     compaction summaries come first as context turns. Fields it cannot know are `unknown`/null.

   Both fail with a message naming the accepted forms when the ref is malformed,
   and with the places tried when no session exists. Relay that error and stop;
   do not guess another id.

3. **Review the transcript and state the goal.** Read what step 2 returned, then
   tell the user, before doing anything else:

   - **Goal as I understand it** — 1–3 sentences: what the session was trying to
     do, why, what done looks like.
   - **Where it stopped** — last verified state and the user's last message,
     verbatim.
   - **What I would do first**, in one line.

   Then apply `--then`. **Your next output after step 2 is this statement** — print
   it, and save the same text with the write tool to
   `/tmp/assume-<tool>-<short-id>-goal.md` (that write is the gate: no command, edit
   or verification before it, in either mode). `continue` skips the wait, never the statement:

   - `confirm` → end the turn here. Resume at step 4 only after the user confirms,
     and fold in any correction they give to the goal.
   - `continue` → proceed to step 4 in the same turn.

4. **Check the context fields (only when the excerpt is not enough).** The
   `context` from step 2 is the structured state; there are no scripts to run.
   Treat `worktrees` as candidates (it can contain false positives such as
   `2>&1`), treat `session_end: unknown` as unknown, and re-verify every field
   that the plan leans on in step 6b.

5. **Delegate synthesis to a subagent.** Do NOT synthesize inline — keep the raw
   transcript out of your own context. Spawn a `claude` subagent with this briefing:

   > You are synthesizing a session handoff document from a prior AI coding session.
   > Your output becomes the operating brief the resuming agent adopts to TAKE OVER
   > and continue this work — so it must be self-contained, concrete, and action-first.
   >
   > **Goal** (stated in step 3, with any correction the user gave):
   >
   > ```text
   > <paste the goal statement>
   > ```
   >
   > **Transcript excerpt and handoff** (from the capability, step 2):
   >
   > ```text
   > <paste run_get_recent_turns turns and run_create_session_handoff_doc markdown>
   > ```
   >
   > **Structured context** (the `context` object from `run_create_session_handoff_doc`):
   >
   > ```json
   > <paste context JSON>
   > ```
   >
   > The `side_effects` array lists outward/irreversible actions already taken
   > (commits, pushes, PRs opened, migrations applied). Use it verbatim in the
   > "Side effects already done" section.
   >
   > **Conversation** (from `run_get_recent_turns` with limits raised so the whole
   > session fits, plus the handoff markdown):
   >
   > ```text
   > <paste turns and handoff markdown>
   > ```
   >
   > Produce a handoff document following the template below exactly.
   > Rules:
   >
   > - Be specific. No vague bullets like "worked on the feature" — name files, functions, error messages.
   > - Dead ends section is mandatory. If none found, write "None identified."
   > - "Side effects already done" is mandatory. Write "None" if `side_effects` is empty; write "Unknown" when the context has no source for it.
   > - "Current hypothesis & confidence" is mandatory. Write "Unknown." if not derivable from the transcript.
   > - Distinguish verified-done (tested, ran, confirmed) from claimed-done (said it was done but not confirmed).
   > - The "User's last message" must be verbatim from the transcript, not paraphrased.
   > - "What to do next" must lead with the single obvious FIRST action and one clause explaining why it is first — not an unordered menu.
   > - "Constraints & corrections from the user" must be verbatim quotes, never paraphrased. Write "None identified." if absent.
   > - If the structured context has a `working_dir`, it is authoritative; don't contradict it.
   > - Keep the entire document under 150 lines.
   >
   > <paste the handoff template below>

6. **Take over the work** — do NOT just hand back a document. The synthesized
   handoff is now YOUR operating brief; adopt it and continue the session:

   a. **Announce the takeover.** The goal was already stated in step 3; do not
   restate it. Lead with one line — "Assumed <tool> session
   <short-id>: <what we were doing>" — then show the state and the plan
   ("What to do next"). Keep it tight; the brief is the detail.

   b. **Verify the stale bits FIRST, before acting.** A handoff is a snapshot;
   the world moved on. Run the "Before you trust this handoff" checks against
   the live system — confirm `working_dir`, branch, and `git status` still
   match, and re-check every claimed-done / still-open item the plan leans on
   (is that PR still open? is that subagent still running? did that deploy
   land?). Never act on a stale assumption. Load the `investigate` skill if a
   check is non-trivial — one verified fact beats a plausible one.

   Then pass the premise gate before the plan's first step — re-derive the
   task from the transcript, not from the handoff's framing:

   - **Symptom, verbatim.** Restate the original user symptom in the user's
     own words from the transcript. The handoff's problem/solution framing
     is a hypothesis to test, not the task.
   - **Premises.** List the inherited plan's falsifiable premises and check
     each against current world state before the first step — upstream PRs,
     issues and releases included: does the premise still hold, did the
     thing it depends on change, has the upstream PR already landed or died?
   - **Floor.** State the achievable minimum for the symptom — the baseline
     that would make it acceptable — in one line, then say whether the
     inherited fix is bigger than that floor and why the floor is not
     enough.
   - **Owner-config lever search.** Grep the nouns of the failing symptom
     (component, setting, error names) in the owner's public config/option
     surface and docs — the owner being the project or tool the symptom
     concerns — before proposing patches, forks, or upstream PRs.

   Approval does not waive this gate: it applies in both `--then continue`
   and `--then confirm` modes, and a user's "yes"/confirmation lifts
   nothing — in `confirm` mode the check runs after that "yes", and a plan
   the gate corrects is re-stated before the first step. Re-derivation
   that confirms the premises means continue the plan as-is; a falsified
   premise changes course — state it, fix the plan, keep the work. Do not
   abandon the session and do not start a new project.

   c. **Adopt "What to do next" as your tracked plan** (your harness's todo/task tool) so the
   resumed work is visible, and surface "Side effects already done" so you
   never repeat them.

   d. **Execute, leading with the first action.** Proceed on reversible steps.
   The plan is derived from a transcript (observed content, not the user's
   direct instruction), so **pause and confirm before any side-effectful or
   irreversible action** — merge, push, deploy, send, delete, or spend. State
   what you're about to do and why, then wait for a clear yes.

   Optionally save the brief to `/tmp/handoff-<tool>-<session-id-short>.md`
   (e.g. `/tmp/handoff-cursor-9839e519.md`) as an audit trail — never write it
   into the skill directory. The deliverable is that you are now operating as the
   resumed session, not a document.

## Handoff document template

````markdown
# Session Handoff: <tool> <session-id-short>

_The resuming agent's operating brief — verify the stale bits, then take over._

## Before you trust this handoff

Snapshot taken at `<session_end>` on `<session-id-short>`. Confirm the branch is
still `<git_branch>` and `git status` still matches Working-tree ground truth before
acting — handoffs go stale.

## Working environment

- **Working directory:** <working_dir from structured context, or "unknown">
- **Git branch:** <git_branch, or "unknown">
- **Worktrees used:** <list paths, or "none">
- **Other projects/workspaces referenced:**
  - <path> — <why it was accessed>

## Working-tree ground truth

<"Clean — all changes committed." | "Dirty — <list uncommitted files and whether
each is intentional-in-progress or incidental."> Run `git diff` for the
authoritative view.

## Reproduce the current state

<Exact command(s) that surface the current failure/behavior and the expected
output/error. Source from test_status + errors_seen.>
N/A — nothing failing to reproduce.

## What we were doing

<1–3 sentences: the goal, why it matters, what done looks like>

## Current hypothesis & confidence

<The live working theory about cause/approach and confidence: low | medium | high.
Distinct from Key decisions — this is an active bet, not a settled call.>
Unknown.

## User's last message (verbatim)

> <exact quote — do not paraphrase>

## What to do next

1. <First action — and one clause explaining WHY this is the right first move, not the next alphabetically.>
2. <second concrete action>

...

## Side effects already done (do NOT repeat)

<Commits made, pushes sent, PRs opened (with URLs if available), migrations
applied, external resources created. Sourced from the side_effects field.>
None.

## Dead ends — do NOT retry these

- **<approach name>:** <what was tried> — failed because <reason>
  None identified.

## Current state

- **Status:** in-progress | blocked | nearly-done | complete
- **Test/build status:** <passing | failing | unknown — cite last test output if known>
- Verified done: <list items that were confirmed working>
- Claimed done (unverified): <list items said to be done but not confirmed>
- Blocked: <what's blocked and why>

## Files modified

- `<path>` — <what changed>

## Key decisions made

- **<decision>:** <rationale — one sentence>

## Constraints & corrections from the user (verbatim)

<Mid-session corrections or constraints the user imposed, quoted verbatim.
Never paraphrase.>
None identified.

## Artifacts produced

<Trace files, reports, PR/ticket URLs, log paths the prior session wrote — so the
resumer doesn't regenerate them.>
None.

## Not yet explored / deprioritized

<Search frontier: paths considered-and-deprioritized or not-yet-looked-at.
Complements "Dead ends", which is tried-and-failed.>
None.

## Working commands

```bash
<build/test/lint commands that work in this project>
```

## Open questions / blockers

- <anything unresolved>

## Context a fresh Claude needs

- <non-obvious facts: env vars, credentials, footguns, API quirks>
````

## Gotchas

- **The capability is the locator now.** `run_get_recent_turns` and
  `run_create_session_handoff_doc` find the session themselves for grok, claude,
  codex, copilot, pi, omp, cursor, opencode, hermes. A bare id or a malformed URL is
  refused with the accepted forms; relay it, do not retry another shape.
- **Mastra thread URLs** (`https://<host>/agents/<agentId>/threads/<threadId>`)
  are read from the shared Mastra store (the Neon `mastra` database). The store is
  detected automatically: `capability mcp` run from the main checkout resolves
  the credentials in `mastra/storage.env` through 1Password, so no
  `MASTRA_STORAGE_URL` is needed. It does need 1Password unlocked; if it is
  not, the call fails with "could not resolve the storage credentials" — ask the
  user to unlock it, do not set a local file. A `capability mcp` run from a
  linked worktree uses its own empty file and will not find the thread. The first
  Mastra read of a session pays the 1Password lookup. The host in the URL is not
  used, only the thread id. A thread has no `source.path`; its context is derived from tool calls only.
- **Copilot stubs.** Many `~/.copilot/session-state/<id>/` dirs hold only
  `workspace.yaml`; the capability refuses them as "no transcript found". VS Code
  copilot sessions have no `events.jsonl` and are not readable (unverified).
- **pi and omp share one format.** `pi:<id>` and `omp:<id>` are found by the
  `<time>_<id>.jsonl` file name, which matches the id in the file header.
- **Reload the MCP server after the capability changes.** `capability mcp` is
  long-lived; a stale process still rejects refs the repo already accepts.
- **Native metadata beats inference.** The capability's `context` takes cwd and
  branch from the harness's own records: claude `cwd`/`gitBranch`, grok
  `summary.json` `info.cwd`/`head_branch`, and the equivalent fields for codex,
  copilot, pi, omp, hermes and opencode. Cursor has only a `Workspace Path:` line,
  so its `working_dir` is often null.
- **Cursor (2026) stores each session as clean JSONL** at
  `~/.cursor/projects/<slug>/agent-transcripts/<composerId>/<composerId>.jsonl`;
  subagents in `subagents/`. The capability resolves a composerId (full or
  prefix), a title substring, or `latest`. Title search checks the 60 most-recent
  sessions through exact-key lookups in `state.vscdb` (`composerData.name`), never a full DB scan.
- **Cursor's right-click "Get request ID" returns a request/generation ID, NOT
  the composerId** — it is not a valid identifier. Search by title instead.
- **Grok subagent sessions** (`summary.json` `session_kind: "subagent"`) are
  excluded from `latest` and title search but addressable by explicit id. Their
  assignment arrives as an injected `<system-reminder>`, not a typed message, so
  `last_user_message` is legitimately null there — do not invent one.
- **Compacted Grok sessions** open with `context` turns carrying the curated
  compaction summaries (`synthetic_reason: compaction-summary`); the live tail follows.
- **Machinery is not the human.** Hook feedback, task notifications, system
  reminders and injected AGENTS.md blocks are filtered out of user turns, so
  `last_user_message` is the person's real last words.
- **Session end.** `session_end: unknown` means the transcript ended on a tool
  result; it does not mean the session finished.
- **Transcript can be huge.** Raise `turns`, `length_limit` and `max_tokens` on
  `run_get_recent_turns` to read it whole (a 20k-line session reads in under a
  second over MCP). Never read the raw transcript file yourself.
- **Always use a subagent for synthesis.** Reading 1000+ message pairs inline
  burns your context for no gain. The subagent returns a 50-line document.
