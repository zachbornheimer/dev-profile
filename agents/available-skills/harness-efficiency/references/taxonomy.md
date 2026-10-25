# Finding taxonomy

Recurring waste, not one ugly turn. Gate: `session_count >= 3` unless the case is
severe. `instruction_bloat` may also fire from file-size × reads.

Never invent harness or model names. Omit a field you cannot measure.

## Required fields

| Field                | Rule                                                     |
| -------------------- | -------------------------------------------------------- |
| `id`                 | Stable `kind:slug` from `fingerprint`                    |
| `kind`               | One of the kinds below                                   |
| `harnesses`          | Measured vendors only; omit if unknown                   |
| `models`             | Measured model ids only; omit if unknown                 |
| `occurrences`        | Event count                                              |
| `session_count`      | Distinct sessions                                        |
| `sessions`           | Session ids                                              |
| `examples`           | Redacted, truncated samples                              |
| `impact`             | Measured only (counts, sizes, durations) — never guessed |
| `proposed_primitive` | From `classify_primitive`                                |
| `proposed_fix`       | Smallest durable change                                  |
| `why_primitive`      | One-line decision-test reason                            |
| `measured`           | `true` if every numeric field came from the index        |

## Kinds

| kind                | What clusters                                                                        |
| ------------------- | ------------------------------------------------------------------------------------ |
| `repeated_shell`    | Normalized command, and consecutive 2-grams                                          |
| `repeated_read`     | Same path                                                                            |
| `repeated_search`   | Same query/pattern                                                                   |
| `repeated_tool_seq` | Tool-name 3-grams                                                                    |
| `correction`        | User text, lowercase first 80 chars                                                  |
| `permission_stop`   | Permission denials / rejections                                                      |
| `retry`             | Error then the same tool                                                             |
| `compaction`        | Compaction events                                                                    |
| `subagent`          | High spawn count                                                                     |
| `test_overuse`      | `tests > 3 ×` non-test shell and `tests >= 10`                                       |
| `long_session`      | `user_turns + agent_turns >= 80`                                                     |
| `instruction_bloat` | Reads of `CLAUDE.md` / `AGENTS.md` / `SKILL.md`                                      |
| `model_routing`     | Tiny sessions (`user_turns <= 2`) on expensive names containing `opus` or `grok-4.6` |
| `skill_self`        | This skill's own loop (re-auditing without a new primitive)                          |

## Prior join

`prior_findings.jsonl` joins on `id`:

| status          | Meaning                       |
| --------------- | ----------------------------- |
| `still_present` | Same id in this run and prior |
| `gone`          | Prior id missing this run     |
| `new`           | This run, not in prior        |
