# AI history UI — thinking glow + action stack

User skill for Claude, Grok, and Codex. Invoke with `/ai-history-ui`.

**Start at [SKILL.md](SKILL.md).** That is the agent entry.

| Path                           | What it is                                            |
| ------------------------------ | ----------------------------------------------------- |
| `SKILL.md`                     | When to load, gotchas, implementation recipe          |
| `SPEC.md`                      | RFC 2119 contract                                     |
| `spec.html`                    | Readable spec — annotated frames, live mock, copy-out |
| `screenshots/`                 | Key frames + crops from the Bevel recording           |
| `tests/spec/traceability.yaml` | Done-gate                                             |
| `agents/openai.yaml`           | Codex display + implicit invocation                   |

The original 38s recording is not bundled (23 MB). Ground truth is the
screenshots plus SPEC.md.

Satisfied when every `traceability.yaml` entry is `status: passing`.
