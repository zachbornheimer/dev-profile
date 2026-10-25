---
name: status-board
description: Use when a session does multi-step work the user will want to check without asking, or when you are not in omp and must put a session on the status board by hand. In omp the board follows your todo list and your pinned decisions automatically; this skill covers what to add and the CLI for other harnesses.
---

# Status board

One page shows every session, project and objective: what is running, done, stalled, and which decisions are waiting for the user. Dashboard: `https://status-board.localhost` (other machines: `http://<this mac>.local:4747/`). Code and docs: `~/Developer/Personal/status-board`.

## In omp: use the todo list, and add what only you know

An extension mirrors your todo list onto the board. Nothing else is required.

- Phase = objective, task = step. The board shows these titles to someone who has not seen the conversation, so name a phase for what it achieves and write a task as what is being done, never "Refactor" or "Verify". Keep the list current: start a task when you begin it, `done` when it is finished, `block` it with the reason when it cannot go on. A blocked task asks the user for nothing; it is only a state.
- To ask the user anything, pin a decision (`pin_decision`) with the question and its options. It is the only thing on the board that needs them, and it clears when answered.
- The user can answer a decision, comment on a card, or ask for an update from the board. These arrive as your next user message: `Decision <id> (…): <choice>` (act on it and call `resolve_decision`), `The user commented on what your status board shows…` or `The user asked for an update from the status board…`. Reply by calling `board_update` with `summary` (1–2 plain sentences, no objective needed); that sentence is shown on your card with its time. Answer a comment there too, not only in chat.
- Call `board_update` only for what the todo list cannot say; all of it is optional, and the board shows nothing in its place:
  - `doneWhen` when a phase starts: how someone could tell it is finished;
  - `step` + `result` when a task finishes: one sentence on what it produced, readable by someone who was not there;
  - optionally `sub` (a short line under the title) or `note` + `noteKind` (reasoning, action, result, decision, question).
  Name the phase and task by the words the todo list uses. These survive later todo updates.
- A session that never uses the todo list never appears. Subagents have no board entry of their own.
- A step left `in_progress` after you stop shows as stalled in 15 minutes. Finish it or block it with a reason before you end.
- Do not mention the board to the user.

## Other harnesses: the CLI

`~/Developer/Personal/status-board/bin/status-board` (or `status-board` when on PATH). Set once: `export STATUS_BOARD_PROJECT=<project> STATUS_BOARD_SESSION=<session>`.

```sh
status-board register  --title "What this session does" --harness claude --agent main:Claude
status-board objective --id redirects --title "…" --done-when "…"
status-board step      --objective redirects --id write --title "…" --agent main --status active
status-board step      --objective redirects --id write --status done --result "Wrote the hook; drafts are skipped."
status-board step      --objective redirects --id test --status blocked --blocker "The staging site is down."
status-board decision  --id 1 --question "Which database?" --option Postgres --option SQLite   # the only way to ask the user
status-board resolve   --id 1                                                                   # answered, or no longer matters
status-board touch                      # proof of life during long work
status-board list                       # the board as text, no server needed
```

Rules the CLI enforces, each refused with the field named and nothing written: `blocked` needs `--blocker`; one `active` step per agent; at most nine options per decision; names are letters, digits, `.`, `_`, `-`. `--result` and `--done-when` are optional. Never edit the JSON files by hand.

## Do not

- Mark a task `done` because you ran out of ideas. `done` means the result sentence is true.
- Put secrets or raw logs in a result, a blocker, a decision or a note. The page shows them as written, to anyone on the network.
- Use the board as a task tracker. Objectives that must survive handoff belong in `atask`.
