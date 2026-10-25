---
name: typesafe-ai
description: >-
  Typesafe skill pick + mega-goal router. For a single atomic task, pick one
  available skill (or say new). For mega / multi-package / multi-repo goals,
  do NOT stay in grok-build-plan — hand off to AgentMux via `am "…"`.
---

# typesafe-ai

## Idiot-proof routing (read first)

| User ask                                                                                   | Do this                                                                                                      |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| One atomic task in one repo                                                                | Pick exactly one skill from `~/.agents/available-skills/` (or `new` if none fit). Load only that `SKILL.md`. |
| Mega / multi-package / multi-repo / overnight fleet / “fix everything in X” spanning repos | **Leave grok-build-plan.** Hand off to AgentMux conductor.                                                   |
| Bare `$HOME` mega `/goal`                                                                  | Refuse. Same handoff.                                                                                        |

### Mega handoff (copy-paste)

```bash
am "<user's mega-goal verbatim>"
```

Equiv: `agentmux run --repo <git-root|AM_REPO> --goal "…" --provider grok`
Alias: `mux` → `am`.

After printing the command (or running it if shell is available), **stop**. Do not fan out subagents under grok-build-plan for a mega-goal.

### What counts as mega (any one → handoff)

- Mentions multiple packages/repos/services, or “whole monorepo”, or “all of …”
- Asks for overnight / fleet / parallel packages
- cwd is `$HOME` / `~` and goal is not a single-file atomic edit
- Would need >1 long-lived worker or cross-repo coordination
- User says “conductor”, “agentmux”, “am”, or “mux”

## Non-mega path (atomic only)

1. List candidates under `~/.agents/available-skills/*/SKILL.md` (names + descriptions only).
2. Pick **one**. If none fit → say `new` (do not invent a skill body inline).
3. `Read` that skill’s `SKILL.md` and follow it.
4. Never dump the whole catalog into the prompt.
5. Do not `hermes skills install` a picked skill into a Hermes profile catalog.
   This skill and `typesafe-skills` live under `~/.agents/available-skills/`.
6. For TypeSafe API design (Choice/Score/Noul/Box, images), load
   `typesafe-skills` (`examples/37-Images-and-Box.md` for pixels). This file is
   only the picker + mega-goal router.

## Grok host note (ZYS-852)

Grok discards UserPromptSubmit `additionalContext`. The companion hook
`typesafe-skill-pick.py` therefore **blocks** mega prompts with a user-visible
reason that includes the `am "…"` command. Honor that block — do not work around it.

## Related

- ZYS-863 AgentMux owns mega-goals + fleet budget
- ZYS-864 `am` daily entry hook
- ZYS-860 refuse bare home-cwd mega `/goal`
- ZYS-854 burn attribution parent
