# Harness map

Parsers live in `scripts/he_parse.py`. This table is the locator only.

`HE_HOME` overrides home. `HE_STATE` defaults to `~/.local/state/harness-efficiency`.

| harness     | path                                                                      | format                                                                                                   |
| ----------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| claude-code | `~/.claude/projects/*/*.jsonl`                                            | JSONL `type` user/assistant; `cwd` / `gitBranch` / `timestamp`; tools in `message.content`               |
| codex       | `~/.codex/sessions/**/*.jsonl`                                            | `session_meta`, `turn_context`, `response_item`, `event_msg`                                             |
| cursor      | `~/.cursor/projects/*/agent-transcripts/*/*.jsonl`                        | `{role, message.content[]}`; legacy `~/.cursor/chats/**/store.db` is discover-only when JSONL is present |
| grok        | `~/.grok/sessions/<encoded-cwd>/<id>/summary.json` + `chat_history.jsonl` | Skip `synthetic_reason`; model is `current_model_id`                                                     |
| opencode    | `~/.local/share/opencode/opencode.db`                                     | `session` / `message` / `part`; tokens/cost on session; never dump the whole DB                          |
| gemini      | `~/.gemini/tmp/*/chats/*.jsonl`                                           | First record is session meta                                                                             |
| copilot     | `~/.copilot/session-state/*/events.jsonl`                                 | Plus `vscode.metadata.json`                                                                              |
| windsurf    | `~/.windsurf`                                                             | No session store; discover reports `no_sessions`                                                         |

Never `rglob` a tree without a file-type filter. Cursor session_count is JSONL
under `agent-transcripts` only. Grok session_count is `*/*/summary.json`.
OpenCode session_count is `SELECT count(*) FROM session`.
