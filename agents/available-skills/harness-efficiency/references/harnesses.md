# Harness map

Only omp and the Codex desktop app are supported. Only Codex sessions are indexed;
there is no omp parser.

The parser lives in `scripts/he_parse.py`. This table is the locator only.
`HE_HOME` overrides home. `HE_STATE` overrides the local index/state directory.

| Harness | Store                          | Notes                                                        |
| ------- | ------------------------------ | ------------------------------------------------------------ |
| codex   | `~/.codex/sessions/**/*.jsonl` | `session_meta`, `turn_context`, `response_item`, `event_msg` |
| omp     | Not indexed                    | No parser in this skill                                      |

Never `rglob` a tree without a file-type filter.
