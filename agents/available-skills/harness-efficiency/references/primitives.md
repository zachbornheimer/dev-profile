# Primitive mapping

Smallest durable fix for a recurring finding. Encode judgment in a skill; encode
mechanics in a script. Do not add a new always-on line to paper over a missing
command.

## Table

| Primitive           | When                                                     | Token cost                                    |
| ------------------- | -------------------------------------------------------- | --------------------------------------------- |
| command / script    | No judgment; same argv every time                        | Zero in the model (user or skill runs it)     |
| skill               | On-demand procedure the model must follow                | Name+description always; body on invoke       |
| slash command       | User-typed trigger for a short recipe                    | Only when the user types it                   |
| subagent            | Output would flood the parent (dump, search, explore)    | Isolated; parent sees the summary             |
| hook                | Must fire even if the model forgets (block, redact, cap) | Zero model tokens; mandatory                  |
| MCP                 | Live external system (Linear, git host)                  | Tool schemas on demand (harness-dependent)    |
| always-on rule      | Fact that is true every turn (`AGENTS.md` / `CLAUDE.md`) | Paid every turn; re-injected after compaction |
| path-scoped rule    | Fact true only under a glob                              | Paid on matching files                        |
| model-routing       | Tiny / mechanical work on a cheap model                  | Saves the expensive turn                      |
| harness config      | Vendor setting (permissions, sandbox, plugins)           | None after the change                         |
| removal             | Existing instruction is the waste                        | Negative cost                                 |
| zq / Evident Output | CLI / presentation output in a zq-using repo             | None if the repo already adopted it           |
| docs                | Human-only context that should not enter the model       | Zero unless someone reads it                  |
| no change           | One-off or already fixed                                 | —                                             |

## Official notes

- Always-on files cost every turn and are re-read after compaction. Facts and
  never-do-X only.
- Skills are progressive disclosure: name+description at start, body on invoke.
- Subagents own their context and must return summaries, not transcripts.
- Hooks are mandatory and token-free. Stop hooks need a rejection cap.
- Slash commands are user-typed; skills are model-invoked.

## Decision test

1. Script if no judgment.
2. Hook if it must fire anyway.
3. `AGENTS.md` if it is an always-true fact.
4. Skill if it is an on-demand procedure.
5. Subagent if the raw output would wreck the parent.
6. Fix or remove an existing instruction before adding another.

## Where it lives

Classify before you create anything. Search for the current owner first.

| Home           | Use when                                                                                             |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| memory         | A compact lesson for the next session. Not task state, secrets, or a procedure a skill already owns. |
| skill          | Judgment: what good looks like, when to stop, how to decide.                                         |
| script         | The same mechanical sequence every time. The script owns arguments, validation, and evidence.        |
| hook           | It must fire even if the model forgets. A blockable failure should not stay a sentence in a skill.   |
| always-on rule | True on every turn.                                                                                  |
| scheduled job  | The operation already works. The job only says when it runs. Do not define the operation here.       |
| nothing        | One-off, speculative, already owned, or more expensive to keep than the failure it prevents.         |

A skill may contain a pipeline. That does not make a second artifact. Keep it in the skill unless a step must survive the session dying, retry on its own, or run under a different model. If you split it, leave the judgment in the skill. Do not copy the skill into every step.

One severe safety miss can become a hook now. Ordinary taste needs the same correction more than once.

For each promotion: cite the sessions, find the current owner, classify, make the smallest change at that owner, replay a prior example or say you did not, and record what you rejected.
