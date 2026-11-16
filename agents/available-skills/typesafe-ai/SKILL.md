---
name: typesafe-ai
description: >-
  Typesafe skill pick + mega-goal router. For a single atomic task, pick one
  available skill (or say new). For mega / multi-package / multi-repo goals,
  file each outcome as an atask objective and delegate instead of working it
  in one session.
---

# typesafe-ai

## Idiot-proof routing (read first)

| User ask                                                                                   | Do this                                                                                                      |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| One atomic task in one repo                                                                | Pick exactly one skill from `~/.agents/available-skills/` (or `new` if none fit). Load only that `SKILL.md`. |
| Mega / multi-package / multi-repo / overnight fleet / “fix everything in X” spanning repos | **Do not work it in one session.** File one `atask` objective per outcome and delegate each.                 |
| Bare `$HOME` mega `/goal`                                                                  | Refuse. Same handoff.                                                                                        |

### Mega handoff

File each outcome with a proof and a regression check, then delegate it:

```bash
atask add "<one outcome>" --proof "run: <cmd>" --regression "run: <cmd>"
```

Run a filed objective with `start_atask_task` (it claims the id into its own worktree and
lands only after `atask verify complete`). After filing, **stop**. Do not fan out subagents
for a mega-goal in the current session.

### What counts as mega (any one → handoff)

- Mentions multiple packages/repos/services, or “whole monorepo”, or “all of …”
- Asks for overnight / fleet / parallel packages
- cwd is `$HOME` / `~` and goal is not a single-file atomic edit
- Would need >1 long-lived worker or cross-repo coordination

## Non-mega path (atomic only)

1. List candidates under `~/.agents/available-skills/*/SKILL.md` (names + descriptions only).
2. Pick **one**. If none fit → say `new` (do not invent a skill body inline).
3. `Read` that skill’s `SKILL.md` and follow it.
4. Never dump the whole catalog into the prompt.
5. This skill and `typesafe-skills` live under `~/.agents/available-skills/`.
6. For TypeSafe API design (Choice/Score/Noul/Box, images), load
   `typesafe-skills` (`examples/37-Images-and-Box.md` for pixels). This file is
   only the picker + mega-goal router.

## Related

- ZYS-860 refuse bare home-cwd mega `/goal`
- ZYS-854 burn attribution parent
