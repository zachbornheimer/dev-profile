# turn-recovery (ZYS-8563)

Resumes an omp turn that a crash cut off, using Neon as the single authority so a second machine reaches the same verdict as the first. It is an omp extension: Herdr already restores the pane and re-runs `omp --resume`, which brings back the conversation but leaves the interrupted turn idle. This closes that gap.

## What already exists, and why this is not a replacement

| Mechanism                                         | Covers                                                                              | Gap this fills                                                                                                            |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Herdr native restore (`resume_agents_on_restore`) | Layout, cwd, `omp --resume <id>` per pane                                           | Conversation returns; the cut-off turn stays idle.                                                                        |
| `omp --restore` (harness)                         | Closes the dangling tool calls and retries the turn, from this machine's transcript | Opt-in per launch, reads only the local transcript, and cannot tell a crash from a turn still running on another machine. |
| `herdr-omp-agent-state.ts`                        | Reports working/idle/blocked to the sidebar                                         | Display only, nothing durable.                                                                                            |

This extension adds a durable, fenced, cross-machine record and a decision step. It sends the agent a notice; it does not edit the transcript or retry tool calls, so `omp --restore` and this extension do not conflict: whichever acts first closes the turn, and the other finds nothing unfinished.

## Lifecycle: what each event means

| omp event                                     | Registry effect                                                                                            |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `agent_start`                                 | New turn, next generation, owner = this process. Any older live turn of the session becomes `stopped`.     |
| heartbeat (15 s)                              | Renews the lease and records tools in flight. A refused heartbeat means another system took the turn over. |
| `tool_execution_start` / `_end`               | Tracks in-flight tools. The `ask` tool moves the turn to `awaiting_input` and back.                        |
| `agent_end` (terminal, not `willContinue`)    | `stop` -> `completed`, `aborted` -> `cancelled`, anything else -> `failed`.                                |
| `session_shutdown` (Ctrl-C, `/quit`, SIGTERM) | `stopped`. Intentional, never resumed.                                                                     |
| none (SIGKILL, power loss, kernel panic)      | The row stays `running` and its lease runs out. This is the only crash signature.                          |

`completed`, `failed`, `cancelled`, `stopped`, `recovered`, `needs_attention` are terminal and absorbing. `awaiting_input` is never resumed.

## Decision on a (re)started session

`session_start` and a `resume` switch read the session's latest turn and decide:

1. No record, terminal state, `awaiting_input`, or this process's own turn: do nothing.
2. Lease younger than 45 s: the owner may be alive on another machine. Wait, re-check when the lease can lapse.
3. Lease expired, and the transcript's last message is a final answer after the turn started: the turn finished and only the stop write was lost. Close it as `completed`; send nothing.
4. A recovery notice was claimed earlier but never acknowledged, and it is already in the transcript: mark it `recovered`; send nothing.
5. Transcript unreadable: `needs_attention`. Never guess.
6. Two recovery attempts already made: `needs_attention`.
7. Otherwise wait one heartbeat period and read again. If anything moved, the owner was only cut off from Neon, so stand down. If nothing moved, claim and send.

The claim is one compare-and-swap `UPDATE` on `(turn_id, generation)` plus a stale lease. Of any number of simultaneous reconnects exactly one gets a row back. It bumps the generation, so the crashed owner, if it revives, is refused on its next heartbeat or stop write. The attempt count and send time are written before the message goes out, so a crash between send and acknowledgement leaves evidence and not a blind retry.

## The notice

Sent with `attribution: "agent"`, `customType: herder-turn-recovery`, `deliverAs: "nextTurn"` plus `triggerTurn`, in the same session, so the model, thinking level and identity are the session's own. It states plainly that it is automated, is not a new user instruction, and adds no authority. It lists tools that were in flight, flags every tool not on the read-only allowlist as possibly having side effects, and tells the agent to re-read what it already did and check real state before repeating any write, push, deploy or message. Unknown tools fail closed as non-idempotent.

## Failure behaviour

- Neon unreachable or a write fails: outcome `unknown`, the pane shows `blocked: turn state unknown`, nothing is sent. The extension retries (up to 12 times) and recovers once Neon is back.
- Registry writes during a live turn are best effort, run on one ordered lane (so `agent_end` can never overtake `agent_start`), and each is bounded to 10 s. A hung or failing registry never blocks or fails the turn itself.
- The audit trail (`herder_turn_events`) records every decision with actor and reason. `/turn-recovery` prints the latest turn and recent decisions in the TUI.

## Install

1. `SESSIONS_DB_URL` must be set (the same Neon URL omp already uses for sessions). Without it the extension does nothing.
2. Put this directory at `~/.config/omp/turn-recovery`. `config/mise.toml` lists that path as a tracked live file (`mode = "track"`, like `fallback-shake`, `hide-evidence` and `thinking`), so mise history checkpoints it once it exists. `mise dot apply` was not run when this was written (mise was unavailable), so check it with `mise dot apply --dry-run` and, if needed, copy the directory by hand.
3. Add it to `~/.omp/agent/config.yml`, then restart omp:

   ```yaml
   extensions:
     - ~/.config/omp/turn-recovery
   ```

The schema is created on first use (`CREATE TABLE IF NOT EXISTS`, guarded by an advisory lock). Tables: `herder_turns`, `herder_turn_events`.

## Test

```sh
TURN_RECOVERY_TEST_DB=postgres://user@127.0.0.1:5432/scratch mise run test:turn-recovery
```

Use a scratch database, never the live `SESSIONS_DB_URL`. Without the variable the database cases skip and only the pure rules run.

## Known limits

- It recovers omp sessions only. Other Herdr agents (claude, codex, ...) have no extension point wired here.
- It resumes when the session is next started or resumed. A pane Herdr could not restore (missing cwd, no reported session reference) is not reached.
- The lease is 45 s: a crashed turn becomes recoverable about that long after its last heartbeat, plus the 16 s confirmation.
- Evidence of completion is the transcript's final assistant answer. A turn that ended in prose but meant to continue would be closed as completed.
- Tools are classified by name. An MCP or custom tool is treated as side-effecting, which only makes the notice more cautious.
- A side-effecting tool is written to the registry when it starts, not at the next heartbeat, so a crash right after a write still names it. Read-only tools are recorded at the next heartbeat only; a crash in that window omits them from the notice, which is harmless because they do not change state.
- A turn taken over by another system is not stopped locally. Its late writes are refused by the registry's fencing, and the pane shows `blocked: this turn was taken over by another system`.
